import json
from datetime import datetime, timezone

from .base_storage import BaseStorage

class GoogleSheetsStorage(BaseStorage):

    def __init__(self, spreadsheet_id, worksheet="Persistence"):
        import os
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        credentials_json = os.environ.get(
            "GOOGLE_SERVICE_ACCOUNT_JSON"
        )

        if not credentials_json:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is missing"
            )

        credentials = Credentials.from_service_account_info(
            json.loads(credentials_json),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets"
            ],
        )

        self.service = build(
            "sheets", "v4",
            credentials=credentials,
            cache_discovery=False,
        )

        self.spreadsheet_id = spreadsheet_id
        self.worksheet = worksheet
        self._ensure_header()

    def _range(self):
        return f"{self.worksheet}!A:C"

    def _ensure_header(self):
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet}!A1:C1",
        ).execute()

        if not result.get("values"):
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.worksheet}!A1:C1",
                valueInputOption="RAW",
                body={"values": [[
                    "key", "value_json", "updated_at"
                ]]},
            ).execute()

    def _rows(self):
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self._range(),
        ).execute()

        return result.get("values", [])

    def get(self, key):
        for row in self._rows()[1:]:
            if row and row[0] == key:
                return json.loads(row[1])
        return None

    def set(self, key, value):
        rows = self._rows()
        now = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(value, ensure_ascii=False)

        for index, row in enumerate(rows[1:], start=2):
            if row and row[0] == key:
                target = f"{self.worksheet}!A{index}:C{index}"
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=target,
                    valueInputOption="RAW",
                    body={"values": [[key, encoded, now]]},
                ).execute()
                return True

        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=self._range(),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[key, encoded, now]]},
        ).execute()

        return True

    def delete(self, key):
        rows = self._rows()

        for index, row in enumerate(rows[1:], start=2):
            if row and row[0] == key:
                self.service.spreadsheets().values().clear(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.worksheet}!A{index}:C{index}",
                ).execute()
                return True

        return False
