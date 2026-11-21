class StateSaver:

    def __init__(self, checkpoint_manager):
        self.checkpoints = checkpoint_manager

    def save(self, checkpoint_name, state):
        return self.checkpoints.save(
            checkpoint_name, state
        )
