from Operator import Operator, States
from time import sleep

operator = Operator()  # Создаём экземпляр оператора (СППР).


# Главный поток
def main_loop():
	while operator.state == States.Connected:
		operator.process()  # Обрабатываем все действия оператора.
		sleep(1)  # Ожидаем 1 секунду и повторяем, пока оператор не отключится.


operator.subscribe(0, main_loop, True)  # Запускаем главный поток при подключении оператора.
operator.wait()  # Ожидаем подключения следующего оператора; повторяем бесконечно.
