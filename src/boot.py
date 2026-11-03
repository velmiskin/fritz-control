# boot.py -- executed on every boot (including wake-boot from deepsleep)
import gc
import esp

esp.osdebug(None)
gc.collect()
