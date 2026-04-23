import os
import sys
from django.apps import AppConfig

class ScannerConfig(AppConfig):
    name = 'scanner'

    def ready(self):
        print(">>> [DIAGNOSTIC] Django is reading ScannerConfig...")
        
        # We check if this is the main server process
        if os.environ.get('RUN_MAIN', None) == 'true':
            print(">>> [DIAGNOSTIC] Ignition switch flipped! Starting Weatherman...")
            from crop_backend import weatherman
            weatherman.start_scheduler()
        else:
            print(">>> [DIAGNOSTIC] Ignored duplicate worker thread.")