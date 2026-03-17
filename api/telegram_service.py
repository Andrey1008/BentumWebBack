import requests
import json
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class TelegramService:
    """Сервис для отправки сообщений в Telegram через бота"""
    
    def __init__(self):
        self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        self.chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)
        self.topic_id = getattr(settings, 'TELEGRAM_TOPIC_ID', 9)  # ID темы для заявок поддержки
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def send_support_request(self, user_data, message, request_type='support'):
        """Отправка заявки в поддержку"""
        
        if not self.bot_token or not self.chat_id:
            logger.error("Telegram bot token or chat ID not configured")
            return False
        
        try:
            # Формируем сообщение
            formatted_message = self._format_support_message(user_data, message, request_type)
            
            # Отправляем сообщение в тему
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': formatted_message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'message_thread_id': self.topic_id  # ID темы для отправки
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Support request sent successfully for user {user_data.get('student_code', 'unknown')}")
                return True
            else:
                logger.error(f"Failed to send Telegram message: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending Telegram message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False
    
    def _format_support_message(self, user_data, message, request_type):
        """Форматирует сообщение для отправки в Telegram"""
        
        # Определяем эмодзи и заголовок в зависимости от типа
        emoji_map = {
            'support': '🆘',
            'bug': '🐛',
            'feature': '💡',
            'question': '❓'
        }
        
        emoji = emoji_map.get(request_type, '📝')
        title_map = {
            'support': 'Новая заявка в поддержку',
            'bug': 'Сообщение об ошибке',
            'feature': 'Предложение по улучшению',
            'question': 'Вопрос от пользователя'
        }
        
        title = title_map.get(request_type, 'Новое сообщение')
        
        # Формируем сообщение
        formatted_message = f"""
{emoji} <b>{title}</b>

👤 <b>Пользователь:</b>
• Имя: {user_data.get('fullname', 'Не указано')}
• Группа: {user_data.get('student_code', 'Не указана')}
• Факультет: {user_data.get('faculty', 'Не указан')}

📝 <b>Сообщение:</b>
{message}

⏰ <b>Время:</b> {user_data.get('created_at', 'Текущее время')}
        """.strip()
        
        return formatted_message
    
    def test_connection(self):
        """Проверка соединения с Telegram API"""
        if not self.bot_token:
            return False, "Bot token not configured"
        
        try:
            url = f"{self.api_url}/getMe"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                bot_info = response.json()
                message = f"Connected to bot: @{bot_info['result']['username']}"
                
                # Проверяем возможность отправки в тему
                if self.chat_id and self.topic_id:
                    try:
                        test_url = f"{self.api_url}/sendMessage"
                        test_payload = {
                            'chat_id': self.chat_id,
                            'text': '🧪 Test message - Bot connection successful',
                            'message_thread_id': self.topic_id
                        }
                        test_response = requests.post(test_url, json=test_payload, timeout=5)
                        
                        if test_response.status_code == 200:
                            message += f"\n✅ Topic {self.topic_id} - OK"
                        else:
                            message += f"\n❌ Topic {self.topic_id} - Error: {test_response.status_code}"
                    except:
                        message += f"\n⚠️ Topic {self.topic_id} - Test failed"
                
                return True, message
            else:
                return False, f"API error: {response.status_code}"
                
        except Exception as e:
            return False, f"Connection error: {str(e)}"

# Глобальный экземпляр сервиса
telegram_service = TelegramService()
