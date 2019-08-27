from Operator import Operator, States
from time import sleep
from random import uniform

operator = Operator()  # Создаём экземпляр оператора (СППР).


# Главный поток
def main_loop():
	time = 0
	while operator.state == States.Connected:
		if time == 10:
			operator.send(load('1.png'), uniform(0.85, 0.99))
		elif time == 10:
			operator.send(load('3.png'), uniform(0.85, 0.99))
		else:
			operator.process()  # Обрабатываем все действия оператора.
		sleep(1)  # Ожидаем 1 секунду и повторяем, пока оператор не отключится.
		time += 1


# Получить фейковое фото
def load(name):
	with open('FakeCamera/' + name, 'rb') as f:
		return f.read()


operator.subscribe(0, main_loop, True)  # Запускаем главный поток при подключении оператора.
print(operator._bot.getMe())
print('Started')
operator.wait()  # Ожидаем подключения следующего оператора; повторяем бесконечно.
