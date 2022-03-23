import json
import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv
from telegram import Bot, error

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

load_dotenv()


PRACTICUM_TOKEN = os.getenv('P_TOKEN')
TELEGRAM_TOKEN = os.getenv('T_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('T_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.debug('Бот запущен!')


class PracticumException(Exception):
    """Исключения бота."""

    pass


def check_tokens():
    """Проверка доступности переменных окружения."""
    if PRACTICUM_TOKEN is None or \
            TELEGRAM_TOKEN is None or \
            TELEGRAM_CHAT_ID is None:
        return False
    return True


def timeout_and_logging(message: str = None, run_error=logging.error):
    """Таймаут увеличивающийся в 2 раза и лог."""
    if message:
        run_error(message)  # Запись в лог
    global time_sleep_error
    logging.debug(f'Timeout: {time_sleep_error}с')
    time.sleep(time_sleep_error)
    time_sleep_error *= 2
    if time_sleep_error >= 51200:
        time_sleep_error = 30
        logging.critical(
            'Проблемы в работе программы. '
        )


def parse_status(homework: dict) -> str:
    """Извлекает из информации о конкретной домашней 
    работе статус этой работы."""
    logging.debug(f"Парсим домашнее задание: {homework}")
    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_STATUSES:
        raise PracticumException(
            "Обнаружен новый статус, отсутствующий в списке!"
        )

    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def get_api_answer(current_timestamp: int) -> list:
    """Получение списка домашних работы от заданного времени."""
    logging.info("Получение ответа от сервера")
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers={'Authorization': f'OAuth {PRACTICUM_TOKEN}'},
            params={'from_date': current_timestamp}
        )
    except requests.exceptions.RequestException as e:
        raise PracticumException(
            "При обработке вашего запроса возникла неоднозначная "
            f"исключительная ситуация: {e}"
        )
    except ValueError as e:
        raise PracticumException(f"Ошибка в значении {e}")
    except TypeError as e:
        raise PracticumException(f"Не корректный тип данных {e}")

    if homework_statuses.status_code != 200:
        logging.debug(homework_statuses.json())
        raise PracticumException(
            f"Ошибка {homework_statuses.status_code} practicum.yandex.ru")

    try:
        homework_statuses_json = homework_statuses.json()
    except json.JSONDecodeError:
        raise PracticumException(
            "Ответ от сервера должен быть в формате JSON"
        )
    logging.info("Получен ответ от сервера")
    return homework_statuses_json


def check_response(response: list) -> list:
    """Проверяет ответ API на корректность."""
    logging.debug("Проверка ответа API на корректность")
    if 'error' in response:
        if 'error' in response['error']:
            raise PracticumException(
                f"{response['error']['error']}"
            )

    if 'code' in response:
        raise PracticumException(
            f"{response['message']}"
        )

    if response['homeworks'] is None:
        raise PracticumException("Задания не обнаружены")

    if not isinstance(response['homeworks'], list):
        raise PracticumException("response['homeworks'] не является списком")
    logging.debug("API проверен на корректность")
    return response['homeworks']


def send_message(bot, message: str):
    """Отправка сообщения в телеграм."""
    log = message.replace('\n', '')
    logging.info(f"Отправка сообщения в телеграм: {log}")
    try:
        return bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except error.Unauthorized:
        timeout_and_logging(
            'Телеграм API: Не авторизован, проверьте TELEGRAM_TOKEN и '
            'TELEGRAM_CHAT_ID '
        )
    except error.BadRequest as e:
        timeout_and_logging(f'Ошибка работы с Телеграм: {e}')
    except error.TelegramError as e:
        timeout_and_logging(f'Ошибка работы с Телеграм: {e}')


def main():
    """
    В ней описана основная логика работы программы.
    Все остальные функции должны запускаться из неё.
    Последовательность действий должна быть примерно такой:
        Сделать запрос к API.
        Проверить ответ.
        Если есть обновления — получить статус работы из обновления и
            отправить сообщение в Telegram.
        Подождать некоторое время и сделать новый запрос.
    """
    if not check_tokens():
        logging.critical("Отсутствует переменная окружения")
        return 0
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())  # начальное значение timestamp или 0

    while True:
        try:
            response_api = get_api_answer(current_timestamp)
            homeworks = check_response(response_api)
            logging.info("Список домашних работ получен")
            if ((type(homeworks) is list)
                    and (len(homeworks) > 0)
                    and homeworks):
                send_message(bot, parse_status(homeworks[0]))
            else:
                logging.info("Задания не обнаружены")
            current_timestamp = response_api['current_date']
            time.sleep(RETRY_TIME)

        except PracticumException as e:
            # send_message(bot, f'Ошибка: practicum.yandex.ru: {e}')
            timeout_and_logging(f'practicum.yandex.ru: {e}')
        except Exception as e:
            timeout_and_logging(
                f'Сбой в работе программы: {e}',
                logging.critical
            )
        else:
            global time_sleep_error
            time_sleep_error = 30


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Выход из программы')
        sys.exit(0)
