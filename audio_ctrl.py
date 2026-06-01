import asyncio
import os
import random
import tempfile
import threading
import time

import pygame
import pyttsx3
import yaml


usb_connected = False
last_audio_error = ""
playback_generation = 0

curpath = os.path.realpath(__file__)
thisPath = os.path.dirname(curpath)
with open(thisPath + '/config.yaml', 'r') as yaml_file:
	config = yaml.safe_load(yaml_file)

current_path = os.path.abspath(os.path.dirname(__file__))
audio_lock = threading.RLock()
play_audio_event = threading.Event()
min_time_bewteen_play = config['audio_config']['min_time_bewteen_play']
current_volume = float(config['audio_config']['default_volume'])

try:
	pygame.mixer.init()
	pygame.mixer.music.set_volume(current_volume)
	usb_connected = True
	print('audio usb connected')
except Exception as e:
	last_audio_error = str(e)
	usb_connected = False
	print('audio usb not connected')

try:
	engine = pyttsx3.init()
	engine.setProperty('rate', config['audio_config']['speed_rate'])
except Exception as e:
	engine = None
	last_audio_error = str(e)
	print(f'pyttsx3 init failed: {e}')


def _set_error(error):
	global last_audio_error
	last_audio_error = str(error)


def _require_audio():
	if not usb_connected:
		raise RuntimeError(last_audio_error or 'audio output is not available')


def _next_generation():
	global playback_generation
	playback_generation += 1
	return playback_generation


def get_audio_status():
	return {
		"audio_available": usb_connected,
		"playing": bool(get_mixer_status()),
		"volume": current_volume,
		"last_error": last_audio_error,
	}


def play_audio(input_audio_file, delete_after=False, generation=None):
	try:
		_require_audio()
		with audio_lock:
			pygame.mixer.music.load(input_audio_file)
			pygame.mixer.music.play()

		while pygame.mixer.music.get_busy():
			time.sleep(0.05)
		time.sleep(min_time_bewteen_play)
	except Exception as e:
		_set_error(e)
		print(f"[audio_ctrl.play_audio] error: {e}")
	finally:
		if delete_after:
			try:
				os.remove(input_audio_file)
			except FileNotFoundError:
				pass
			except Exception as e:
				print(f"[audio_ctrl.play_audio] cleanup error: {e}")
		if generation is None or generation == playback_generation:
			play_audio_event.clear()


def play_random_audio(input_dirname, force_flag):
	if not usb_connected:
		return False
	audio_files = [f for f in os.listdir(current_path + "/sounds/" + input_dirname) if f.endswith((".mp3", ".wav"))]
	if not audio_files:
		return False
	audio_file = random.choice(audio_files)
	return play_audio_thread(current_path + "/sounds/" + input_dirname + "/" + audio_file, interrupt=force_flag)


def play_audio_thread(input_file, interrupt=False, delete_after=False):
	_require_audio()
	with audio_lock:
		if interrupt:
			pygame.mixer.music.stop()
			play_audio_event.clear()
		elif play_audio_event.is_set():
			return False

		generation = _next_generation()
		play_audio_event.set()
		audio_thread = threading.Thread(
			target=play_audio,
			args=(input_file, delete_after, generation),
			daemon=True,
		)
		audio_thread.start()
	return True


def play_file(audio_file):
	audio_file = current_path + "/sounds/" + audio_file
	return play_audio_thread(audio_file)


def get_mixer_status():
	if not usb_connected:
		return False
	return pygame.mixer.music.get_busy()


def set_audio_volume(input_volume):
	global current_volume
	_require_audio()
	input_volume = float(input_volume)
	if input_volume > 2:
		input_volume = 2
	elif input_volume < 0:
		input_volume = 0
	current_volume = input_volume
	pygame.mixer.music.set_volume(min(input_volume, 1))
	return current_volume


def set_min_time_between(input_time):
	global min_time_bewteen_play
	_require_audio()
	min_time_bewteen_play = input_time


def play_speech(input_text):
	try:
		_require_audio()
		if engine is None:
			raise RuntimeError('pyttsx3 engine is not available')
		engine.say(input_text)
		engine.runAndWait()
	except Exception as e:
		_set_error(e)
		print(f"[audio_ctrl.play_speech] error: {e}")
	finally:
		play_audio_event.clear()


def play_speech_thread(input_text):
	_require_audio()
	if play_audio_event.is_set():
		return False
	play_audio_event.set()
	speech_thread = threading.Thread(target=play_speech, args=(input_text,), daemon=True)
	speech_thread.start()
	return True


def synthesize_edge_tts(input_text, output_file, voice, rate):
	try:
		import edge_tts
	except ImportError as e:
		raise RuntimeError('edge-tts is not installed in the current Python environment') from e

	async def _save():
		communicate = edge_tts.Communicate(input_text, voice=voice, rate=rate)
		await communicate.save(output_file)

	asyncio.run(_save())


def cleanup_tts_cache(cache_dir):
	if not os.path.isdir(cache_dir):
		return
	for filename in os.listdir(cache_dir):
		if not filename.startswith('tts_') or not filename.endswith('.mp3'):
			continue
		try:
			os.remove(os.path.join(cache_dir, filename))
		except FileNotFoundError:
			pass
		except Exception as e:
			print(f"[audio_ctrl.cleanup_tts_cache] error: {e}")


def apply_tts_gain(input_file, volume):
	if volume <= 1:
		return False
	try:
		from pydub import AudioSegment
		import imageio_ffmpeg
	except ImportError as e:
		raise RuntimeError('pydub or imageio-ffmpeg is not installed; cannot amplify TTS above 100%') from e

	gain_db = 20 * (volume - 1)
	AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
	audio = AudioSegment.from_file(input_file, format='mp3')
	(audio + gain_db).export(input_file, format='mp3')
	return True


def play_edge_tts_thread(input_text, voice, rate, volume, cache_dir):
	_require_audio()
	text = str(input_text or '').strip()
	if not text:
		raise ValueError('播报文本不能为空')
	if len(text) > 500:
		raise ValueError('播报文本过长，请控制在 500 字以内')

	set_audio_volume(volume)
	stop()
	cleanup_tts_cache(cache_dir)
	os.makedirs(cache_dir, exist_ok=True)
	temp_file = tempfile.NamedTemporaryFile(prefix='tts_', suffix='.mp3', dir=cache_dir, delete=False)
	temp_path = temp_file.name
	temp_file.close()

	try:
		synthesize_edge_tts(text, temp_path, voice, rate)
		amplified = apply_tts_gain(temp_path, current_volume)
		started = play_audio_thread(temp_path, interrupt=True, delete_after=True)
		if not started:
			raise RuntimeError('audio playback did not start')
	except Exception:
		try:
			os.remove(temp_path)
		except FileNotFoundError:
			pass
		raise

	return {
		"message": "TTS 播报已开始",
		"voice": voice,
		"rate": rate,
		"volume": current_volume,
		"amplified": amplified,
		"text_length": len(text),
	}


def stop():
	if not usb_connected:
		return False
	with audio_lock:
		_next_generation()
		pygame.mixer.music.stop()
		play_audio_event.clear()
	return True


if __name__ == '__main__':
	play_audio_thread("/home/ws/ugv_rpi/sounds/others/Boomopera_-_You_Rock_Full_Length.mp3")
	time.sleep(100)
