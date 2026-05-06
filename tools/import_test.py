import importlib.util, sys
spec = importlib.util.spec_from_file_location('vis','c:/repos/SonicHalo/src/pyqt5_audio_visualiser_optimise.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('IMPORT_OK')
