import json
import logging
import sys
from datetime import datetime, timedelta
from enum import IntEnum
from io import BytesIO, StringIO
from random import randint, random
from time import sleep
from text2pdf import pyText2Pdf

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.utils import request

from IOperator import IOperator


class States(IntEnum):
	Disconnected = 0
	Authentication = 1
	Connected = 2


class Operator(IOperator):
	"""Икапсулирует работу СППР и взаимодействие с человеком-оператором."""

	def __init__(self):
		"""Икапсулирует работу СППР и взаимодействие с человеком-оператором."""
		# Create fields
		self._detect_frame = None
		self._last_frame = None
		self._score = -1
		self._events = []
		self._decisions = {}
		self._id = None
		self._offset = 0
		self.state = States.Disconnected
		# Load config
		with open('config.json', 'r', encoding='utf-8') as f:
			self._config = json.loads(f.read())
		# Init fields
		self._post_time = datetime.now() - timedelta(seconds=10 * self._config['timeouts']['detection'])
		self.__register_events(3)
		# Create bot
		self._bot = Bot(token=self._config['telegram']['token'], request=request.Request(
			proxy_url=self._config['telegram']['proxy']['url'],
			urllib3_proxy_kwargs=self._config['telegram']['proxy']['auth']))
		# Set log file as <module name>.log
		logging.basicConfig(format=u'%(levelname)-8s [%(asctime)s] %(message)s', level=logging.INFO, filename=sys._getframe(0).f_code.co_filename.replace('<', '').replace('>', '') + '.op.log')

	def __register_events(self, count):
		"""Зарегистрировать указанное количество событий. Их ID будут начинаться с 0 до count-1."""
		self._events = [[] for x in range(count)]

	def __generate_decision_id(self):
		"""Сгенерировать уникальный ID для фотографии."""
		decision_id = randint(1, 1000000)
		while decision_id in self._decisions:
			decision_id = randint(1, 1000000)
		return str(decision_id)

	def __callback(self, index, *args):
		"""Вызвать событие index."""
		if index < 0 or index >= len(self._events):
			raise 'Unknown event ' + str(index) + ' .'
		results = []
		for cb in self._events[index]:
			res = cb(*args)
			if res is not None:
				results.append(res)
		return results

	def process(self):
		"""Выполнить такт процесса - цикл главного потока СППР."""
		self._update()
		self._post()
		self._ignore()

	def _update(self):
		"""Обработать входящие сообщения."""
		updates = self._bot.get_updates(offset=self._offset)  # TODO: проверить offset=-1
		if len(updates) == 0:
			return
		for update in updates:
			if update.message:
				if self.state == States.Disconnected:
					if updates.index(update) == len(updates) - 1:
						update.message.reply_text('Вы пытаетесь подключиться к дрону Альфа. Отправьте пароль.')
					self._id = update.message.chat.id
					self.state = States.Authentication
				else:
					if update.message.chat.id != self._id:
						if updates.index(update) == len(updates) - 1:
							update.message.reply_text('Дроном Альфа уже управляет другой оператор. Попробуйте подключиться позже.')
					else:
						if self.state == States.Authentication:
							if update.message.text != self._config['password']:
								if updates.index(update) == len(updates) - 1:
									update.message.reply_text('Неверный пароль. Попробуйте ещё раз.')
							else:
								if updates.index(update) == len(updates) - 1:
									update.message.reply_text('Вы успешно подключились. Теперь вы можете отправлять команды и получать уведомления от бота Альфа.')
								self.state = States.Connected
								self.__callback(0)
						else:
							if update.message.text == '/stop':
								if updates.index(update) == len(updates) - 1:
									update.message.reply_text('Вы успешно отключились от бота Альфа.')
								self.state = States.Disconnected
								self._id = None
								self.__callback(1)
							elif update.message.text == 'фото':
								if self._last_frame is not None:
									self._bot.send_photo(self._id, self.stream_frame(self._last_frame), caption='Текущее изображение')
							elif update.message.text == 'Начать мониторинг':
								update.message.reply_text('подготовка к взлету...')
								update.message.reply_text('взлёт')
								update.message.reply_text('начал мониторинг ' + datetime.now().time().strftime("%H:%M:%S"))
							elif update.message.text == 'Закончить мониторинг':
								update.message.reply_text('поиск подходящего места для посадки...')
								update.message.reply_text('подготовка к посадке')
								update.message.reply_text('посадка произведена успешно ' + datetime.now().time().strftime("%H:%M:%S"))
							elif update.message.text == 'Отчёт':
								update.message.reply_text('Сбор данных...')
								text = 'CO2: ' + str(round(400 * (1 + random.random() * 2 * 0.25 - 0.25), 3)) + '\r\nSO2: ' + str(round(0.03 * (1 + random.random() * 2 * 0.25 - 0.25), 3)) + '\r\nCO: ' + str(round(0.9 * (1 + random.random() * 2 * 0.25 - 0.25), 3)) + '\r\nNO: ' + str(round(0.008 * (1 + random.random() * 2 * 0.25 - 0.25), 3))
								# convert text to pdf
								pdfclass = pyText2Pdf()
								input_stream = StringIO(text)
								output_stream = BytesIO()
								pdfclass.MemoryConvert(input_stream, output_stream, 'Copter results')
								output_stream.seek(0)
								self._bot.send_document(self._id, output_stream, caption='Данные с датчиков')
			elif update.callback_query:
				data = update.callback_query.data.split('-')
				type = data.pop(0)
				if type == 'decision':
					self._decide(*data)
		self._offset = updates[len(updates) - 1].update_id + 1

	def _post(self):
		"""Отправить распознанную фотографию оператору."""
		if self.state == States.Connected and self._detect_frame is not None and (datetime.now() - self._post_time).seconds > self._config['timeouts']['detection']:
			decision_id = self.__generate_decision_id()
			callback_prefabs = ['decision-' + decision_id + '-' + x for x in ['ignore', 'alert']]
			decision = {'time': datetime.now(),
						'id': decision_id,
						'message': {
							'id': self._bot.send_photo(self._id, self.stream_frame(self._detect_frame), caption='Обнаружена опасность!', reply_markup=InlineKeyboardMarkup([
								[
									InlineKeyboardButton("Ложное срабатывание", callback_data=callback_prefabs[0])
								], [
									InlineKeyboardButton("Вызвать спасателей", callback_data=callback_prefabs[1])
								]])).message_id,
							'operator': self._id}
						}
			self._decisions[decision_id] = decision
			self._detect_frame = None
			self._score = -1
			self._post_time = datetime.now()

	def _ignore(self):
		"""Игнорировать все неотмеченные оператором фотографии."""
		if len(self._decisions) == 0:
			return
		for decision in self._decisions.copy().values():  # copy due to possibility of an deleting event (ignore)
			if (datetime.now() - decision['time']).seconds >= self._config['timeouts']['decision']:
				self._decide(decision['id'], 'ignore')

	def _decide(self, decision_id, action):
		"""Обработать реакцию на ЧС."""
		if decision_id not in self._decisions or action not in ['ignore', 'alert']:
			return
		text = 'Событие проигнорировано.' if action == 'ignore' else 'Вызваны службы МЧС.'
		self._bot.edit_message_caption(chat_id=self._decisions[decision_id]['message']['operator'], message_id=self._decisions[decision_id]['message']['id'], caption=text)  # delete buttons
		del self._decisions[decision_id]

	def stream_frame(self, frame):
		"""Кодирует кадр в поток формата изображения с помощью callback №2."""
		encoded = self.__callback(2, frame)
		stream = BytesIO()
		stream.write(encoded[-1] if len(encoded) > 0 else frame)
		stream.seek(0)
		return stream

	def send(self, photo, score):
		"""Отправить фотографию (кадр) в СППР.

		photo - байтовое представление фотографии (формат задаётся телеграммом).

		score - вероятность распознания на фотографии черезвычайного события."""
		self._last_frame = photo
		if score > self._config['alert_threshold'] and score > self._score:
			self._detect_frame = self._last_frame
		self.process()

	def subscribe(self, event, callback, unique=False):
		"""Подписаться на событие.

		event - номер события.

		callback - функция, которая будет вызвана при наступлении события.

		unique - запретить подписываться одной функции несколько раз?"""
		if event < 0 or event >= len(self._events):
			raise 'Unknown event ' + str(event) + ' .'
		if unique and callback in self._events[event]:
			raise 'Callback has been already subscribed to event ' + str(event) + '.'
		self._events[event].append(callback)

	def unsubscribe(self, event, callback):
		"""Отписаться от события. Выбрасывает исключение, если функция не была подписана на указанное событие.

		event - номер события.

		callback - функция, которая подписана на событие."""
		if event < 0 or event >= len(self._events):
			raise 'Unknown event ' + str(event) + ' .'
		self._events[event].remove(callback)

	def wait(self, loop=True):
		"""Заблокировать поток и ожидать подключения оператора.

		loop - ожидать следующего оператора после отключения последнего?"""
		while True:
			while self.state != States.Connected:
				self.process()
				sleep(1)
			if not loop:
				break
