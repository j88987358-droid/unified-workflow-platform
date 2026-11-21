class RecoveryIntegration:

    def __init__(self, recovery_manager):
        self.recovery_manager = recovery_manager

    def recover_component(self, checkpoint_name):
        return self.recovery_manager.recover(
            checkpoint_name
        )
