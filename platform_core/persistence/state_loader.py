class StateLoader:

    def __init__(self, checkpoint_manager):
        self.checkpoints = checkpoint_manager

    def restore(self, checkpoint_name):
        result = self.checkpoints.load(checkpoint_name)

        if result is None:
            return None

        return result.get("state")
