from asyncio.log import logger
import json
import logging
import os
import time

import requests
import telegram

from dotenv import load_dotenv

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


logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s - %(name)s'
)
logger = logging.getLogger(__name__)
logger.addHandler(
    logging.StreamHandler()
)


class TheAnswerIsNot200Error(Exception):
    """Ответ сервера не равен 200."""


class EmptyDictionaryOrListError(Exception):
    """Пустой словарь или список."""


class UndocumentedStatusError(Exception):
    """Недокументированный статус."""


class RequestExceptionError(Exception):
    """Ошибка запроса."""


def send_message(bot, message):
    '''Сообщение в телегу'''
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(
            f'Сообщение в Телеграм отправлено: {message}'
        )
    except telegram.TelegramError as telegram_error:
        logger.error(
            f'Сообщение в Telegram не отправлено: {telegram_error}'
        )


def get_api_answer(current_timestamp):
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    headers = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
    try:
        response = requests.get(headers=headers, params=params)
        if response.status_code != 200:
            code_api_msg = (
                f' Код ответа API: {response.status_code}')
            logger.error(code_api_msg)
            raise TheAnswerIsNot200Error(code_api_msg)
        return response.json()
    except requests.exceptions.RequestException as request_error:
        code_api_msg = f'Код ответа API (RequestException): {request_error}'
        logger.error(code_api_msg)
        raise RequestExceptionError(code_api_msg)
    except json.JSONDecodeError as value_error:
        code_api_msg = f'Код ответа API (ValueError): {value_error}'
        logger.error(code_api_msg)
        raise json.JSONDecodeError(code_api_msg)


def extracted_from_parse_status(arg0, arg1):
    code_api_msg = f'{arg0}{arg1}'
    logger.error(code_api_msg)
    raise UndocumentedStatusError(code_api_msg)


def check_response(response):
    if response.get('homeworks') is None:
        code_api_msg = (
            'Ошибка ключа homeworks или response'
            'имеет неправильное значение.')
        logger.error(code_api_msg)
        raise EmptyDictionaryOrListError(code_api_msg)
    if response['homeworks'] == []:
        return {}
    status = response['homeworks'][0].get('status')
    if status not in HOMEWORK_STATUSES:
        code_api_msg = f'Ошибка недокументированный статус: {status}'
        logger.error(code_api_msg)
        raise UndocumentedStatusError(code_api_msg)
    return response['homeworks'][0]


def parse_status(homework):
    status = homework.get('status')
    homework_name = homework.get('homework_name')
    if status is None:
        extracted_from_parse_status(
            'Ошибка пустое значение status: ', status)
    if homework_name is None:
        extracted_from_parse_status(
            'Ошибка пустое значение homework_name: ', homework_name)
    verdict = HOMEWORK_STATUSES[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка наличия токенов."""
    no_tokens_msg = (
        'Программа принудительно остановлена. '
        'Отсутствует обязательная переменная окружения:')
    tokens_bool = True
    if PRACTICUM_TOKEN is None:
        tokens_bool = False
        logger.critical(
            f'{no_tokens_msg} PRACTICUM_TOKEN')
    if TELEGRAM_TOKEN is None:
        tokens_bool = False
        logger.critical(
            f'{no_tokens_msg} TELEGRAM_TOKEN')
    if TELEGRAM_CHAT_ID is None:
        tokens_bool = False
        logger.critical(
            f'{no_tokens_msg} CHAT_ID')
    return tokens_bool


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    tmp_status = 'reviewing'
    errors = True
    while True:
        try:
            response = get_api_answer(ENDPOINT, current_timestamp)
            homework = check_response(response)
            if homework and tmp_status != homework['status']:
                message = parse_status(homework)
                send_message(bot, message)
                tmp_status = homework['status']
            logger.info(
                'Изменений нет, ждем 10 минут и проверяем API')
            time.sleep(RETRY_TIME)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if errors:
                errors = False
                send_message(bot, message)
            logger.critical(message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
