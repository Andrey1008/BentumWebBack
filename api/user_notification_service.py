import requests
import logging
from django.conf import settings
from django.utils import timezone
from datetime import datetime

logger = logging.getLogger(__name__)

class UserNotificationService:
    """Сервис для отправки уведомлений о новых пользователях в Telegram"""
    
    def __init__(self):
        self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        self.chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)
        self.new_users_topic_id = getattr(settings, 'TELEGRAM_NEW_USERS_TOPIC_ID', 3)  # ID темы для новых пользователей
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def send_new_user_notification(self, user_data):
        """Отправка уведомления о новом пользователе"""
        
        if not self.bot_token or not self.chat_id:
            logger.error("Telegram bot token or chat ID not configured for user notifications")
            return False
        
        try:
            # Формируем сообщение о новом пользователе
            message = self._format_new_user_message(user_data)
            
            # Отправляем сообщение в тему для новых пользователей
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'message_thread_id': self.new_users_topic_id  # ID темы для новых пользователей
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"New user notification sent for user {user_data.get('student_code', 'unknown')}")
                return True
            else:
                logger.error(f"Failed to send new user notification: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error when sending new user notification: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error sending new user notification: {str(e)}")
            return False
    
    def _format_new_user_message(self, user_data):
        """Форматирует сообщение о новом пользователе"""
        
        # Получаем текущее время
        current_time = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Определяем курс на основе номера группы
        course = self._get_course_from_student_code(user_data.get('student_code', ''))
        
        message = f"""👤 <b>Новый пользователь в системе</b>

📋 <b>Информация о пользователе:</b>
• <b>Имя:</b> {user_data.get('fullname', 'Не указано')}
• <b>Группа:</b> {user_data.get('student_code', 'Не указана')}
• <b>Факультет:</b> {user_data.get('faculty', 'Не указан')}
• <b>Курс:</b> {course}

🎓 <b>Данные для связи:</b>
• <b>ID пользователя:</b> {user_data.get('id', 'Не указан')}
• <b>Дата регистрации:</b> {current_time}

🔔 <b>Статус:</b> ✅ Активен

<i>Пользователь успешно зарегистрирован в системе BentumWeb</i>"""
        
        return message
    
    def _get_course_from_student_code(self, student_code):
        """Определяет курс на основе номера группы"""
        if not student_code or len(student_code) < 8:
            return "Не определен"
        
        try:
            # Извлекаем последние две цифры года поступления
            year_suffix = student_code[6:8]
            admission_year = 2000 + int(year_suffix)
            
            # Определяем текущий курс
            current_year = timezone.now().year
            current_month = timezone.now().month
            
            # Учебный год начинается в сентябре
            if current_month >= 9:
                course = current_year - admission_year + 1
            else:
                course = current_year - admission_year
            
            # Ограничиваем курс от 1 до 5
            if course < 1:
                course = 1
            elif course > 5:
                course = "Выпускник"
            
            return f"{course} курс" if isinstance(course, int) else course
            
        except (ValueError, IndexError):
            return "Не определен"
    
    def test_connection(self):
        """Тест соединения для уведомлений о новых пользователей"""
        
        if not self.bot_token or not self.chat_id:
            return {
                'success': False,
                'error': 'Bot token or chat ID not configured',
                'topic_id': self.new_users_topic_id
            }
        
        try:
            test_message = f"""🧪 <b>Тест уведомлений о новых пользователях</b>

✅ Сервис уведомлений работает корректно
📱 Тема для новых пользователей: {self.new_users_topic_id}
⏰ Время теста: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}

<i>Это тестовое сообщение для проверки работы уведомлений</i>"""
            
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': test_message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'message_thread_id': self.new_users_topic_id
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'Test notification sent successfully',
                    'topic_id': self.new_users_topic_id,
                    'response': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'Failed to send test: {response.status_code} - {response.text}',
                    'topic_id': self.new_users_topic_id
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'topic_id': self.new_users_topic_id
            }
