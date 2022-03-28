import json
import logging
import os
import time
import telegram

import requests
from dotenv import load_dotenv
from telegram import Bot
from exceptions import PracticumException

logger = logging.getLogger(__name__)
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


def check_tokens():
    """Проверка доступности переменных окружения."""
    return all((PRACTICUM_TOKEN,
                TELEGRAM_TOKEN,
                TELEGRAM_CHAT_ID)
               )


def parse_status(homework: dict) -> str:
    """Извлекает из информации о конкретной домашней работе и статус."""
    logging.debug(f'Парсим домашнее задание: {homework}')
    homework_name = homework['homework_name']
    homework_status = homework['status']

    if not homework_status:
        raise PracticumException(
            'Обнаружен новый статус, отсутствующий в списке!'
        )
    if not homework_name:
        raise PracticumException(
            'Не обнаружено имя домашней работы'
        )
    if homework_status in HOMEWORK_STATUSES:
        verdict = HOMEWORK_STATUSES[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    else:
        raise PracticumException('Неизвестный статус работы!')


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
            'При обработке вашего запроса возникла неоднозначная'
            f'исключительная ситуация: {e}'
        )

    if homework_statuses.status_code != 200:
        logging.debug(homework_statuses.json())
        raise PracticumException(
            f'Ошибка {homework_statuses.status_code} practicum.yandex.ru'
        )

    try:
        homework_statuses_json = homework_statuses.json()
    except json.JSONDecodeError:
        raise PracticumException(
            'Ответ от сервера должен быть в формате JSON'
        )
    logging.info("Получен ответ от сервера")
    return homework_statuses_json


def check_response(response: list) -> list:
    """Проверяет ответ API на корректность."""
    logging.debug('Проверка ответа API на корректность')

    if response['homeworks'] is None:
        raise PracticumException("Задания не обнаружены")

    if not isinstance(response.get('homeworks'), list):
        raise TypeError("response['homeworks'] не является списком")
    logging.debug("API проверен на корректность")
    return response['homeworks']


def send_message(bot, message: str):
    """Отправка сообщения в телеграм."""
    log = message.replace('\n', '')
    logging.info(f"Отправка сообщения в телеграм: {log}")
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.error.TelegramError as error:
        logger.error(f'Возникла ошибка Телеграм: {error.message}')
        raise telegram.error.TelegramError(f'Ошибка при отправке: {message}')


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
            if (
                (isinstance(homeworks) is list)
                and (len(homeworks) > 0)
                and homeworks
            ):
                send_message(bot, parse_status(homeworks[0]))
            else:
                logging.info("Задания не обнаружены")
            current_timestamp = response_api['current_date']

        except Exception as error:
            message = f'Бот столкнулся с ошибкой: {error}'
            logger.exception(message)
            send_message(bot, message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Выход из программы')
