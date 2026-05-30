import threading
import time


class StandbyManager:
    def __init__(self, cvf, base, audio_ctrl, config):
        self.cvf = cvf
        self.base = base
        self.audio_ctrl = audio_ctrl
        self.config = config
        self.mode = "active"
        self.last_error = ""
        self.last_message = "System active"
        self.updated_at = time.time()
        self._lock = threading.RLock()

    def get_status(self):
        return {
            "power_mode": self.mode,
            "camera_active": self.cvf.is_camera_active(),
            "last_error": self.last_error,
            "message": self.last_message,
            "updated_at": self.updated_at,
        }

    def _touch(self, message):
        self.updated_at = time.time()
        self.last_message = message
        self.cvf.info_update(message, (79, 245, 192), 0.5)

    def enter_standby(self):
        with self._lock:
            if self.mode == "standby":
                self._touch("Standby already enabled")
                return self.get_status()

            self.base.base_json_ctrl({"T": self.config['cmd_config']['cmd_movition_ctrl'], "L": 0, "R": 0})
            self.base.lights_ctrl(0, 0)
            self.cvf.set_movtion_lock(True)
            self.cvf.set_standby(True)
            self.mode = "standby"
            self.last_error = ""
            self._touch("Standby enabled")
            return self.get_status()

    def wake_up(self):
        with self._lock:
            if self.mode == "active":
                self._touch("System already active")
                return self.get_status()

            if not self.cvf.set_standby(False):
                self.last_error = self.cvf.camera_error or "Camera wake failed"
                self._touch("Wake failed")
                return self.get_status()

            if self.config['base_config']['module_type'] == 1:
                self.base.base_json_ctrl({
                    "T": self.config['cmd_config']['cmd_arm_ctrl_ui'],
                    "E": self.config['args_config']['arm_default_e'],
                    "Z": self.config['args_config']['arm_default_z'],
                    "R": self.config['args_config']['arm_default_r'],
                })
            else:
                self.base.gimbal_ctrl(0, 0, 200, 10)

            self.audio_ctrl.play_random_audio("connected", False)
            self.mode = "active"
            self.last_error = ""
            self._touch("System active")
            return self.get_status()

    def toggle(self):
        if self.mode == "active":
            return self.enter_standby()
        return self.wake_up()

