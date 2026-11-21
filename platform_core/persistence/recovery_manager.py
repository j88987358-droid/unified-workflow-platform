class RecoveryManager:

    def __init__(self, state_loader):
        self.state_loader = state_loader

    def recover(self, checkpoint_name):
        state = self.state_loader.restore(checkpoint_name)

        if state is None:
            return {
                "recovered": False,
                "state": None,
            }

        return {
            "recovered": True,
            "state": state,
        }
