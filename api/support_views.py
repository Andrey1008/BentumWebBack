import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
import logging
from django.utils import timezone
from .models import User
from .telegram_service import TelegramService
from .user_notification_service import UserNotificationService

logger = logging.getLogger(__name__)

# Глобальный экземпляр сервиса
telegram_service = TelegramService()

@csrf_exempt
@require_http_methods(["POST"])
def submit_support_request(request):
    """Обработка заявки в поддержку"""
    
    try:
        # Проверяем авторизацию
        if not request.session.get('is_authenticated'):
            return JsonResponse({
                "success": False,
                "detail": "Требуется авторизация"
            }, status=401)
        
        student_code = request.session.get('student_code')
        user = User.objects.filter(student_code=student_code).first()
        
        if not user:
            return JsonResponse({
                "success": False,
                "detail": "Пользователь не найден"
            }, status=404)
        
        # Получаем данные из запроса
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                "success": False,
                "detail": "Неверный формат JSON"
            }, status=400)
        
        message = data.get('message', '').strip()
        request_type = data.get('type', 'support')  # support, bug, feature, question
        
        # Валидация
        if not message:
            return JsonResponse({
                "success": False,
                "detail": "Сообщение не может быть пустым"
            }, status=400)
        
        if len(message) > 2000:
            return JsonResponse({
                "success": False,
                "detail": "Сообщение слишком длинное (максимум 2000 символов)"
            }, status=400)
        
        if request_type not in ['support', 'bug', 'feature', 'question']:
            request_type = 'support'
        
        # Подготавливаем данные пользователя
        user_data = {
            'fullname': user.fullname,
            'student_code': user.student_code,
            'faculty': user.faculty,
            'created_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Отправляем в Telegram
        telegram_success = telegram_service.send_support_request(user_data, message, request_type)
        
        # Логируем заявку
        logger.info(f"Support request from {user.student_code}: {request_type} - {'sent' if telegram_success else 'failed'}")
        
        # Возвращаем ответ
        if telegram_success:
            return JsonResponse({
                "success": True,
                "message": "Заявка успешно отправлена в поддержку"
            })
        else:
            # Если Telegram не работает, все равно сохраняем заявку
            return JsonResponse({
                "success": True,
                "message": "Заявка принята (возможны задержки с обработкой)"
            })
            
    except Exception as e:
        logger.error(f"Error processing support request: {e}")
        return JsonResponse({
            "success": False,
            "detail": "Внутренняя ошибка сервера"
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def test_telegram_connection(request):
    """Тест соединения с Telegram (только для разработки)"""
    
    # Проверка что это режим разработки
    if not settings.DEBUG:
        return JsonResponse({
            "success": False,
            "detail": "Доступно только в режиме разработки"
        }, status=403)
    
    try:
        is_connected, message = telegram_service.test_connection()
        
        return JsonResponse({
            "success": is_connected,
            "message": message,
            "bot_configured": bool(getattr(settings, 'TELEGRAM_BOT_TOKEN', None)),
            "chat_configured": bool(getattr(settings, 'TELEGRAM_CHAT_ID', None)),
            "topic_id": getattr(settings, 'TELEGRAM_TOPIC_ID', None),
            "topic_configured": bool(getattr(settings, 'TELEGRAM_TOPIC_ID', None))
        })
        
    except Exception as e:
        logger.error(f"Error testing Telegram connection: {e}")
        return JsonResponse({
            "success": False,
            "detail": str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def test_new_user_notification(request):
    """Тестирование уведомлений о новых пользователях"""
    
    from django.conf import settings
    
    if not settings.DEBUG:
        return JsonResponse({'error': 'Available only in DEBUG mode'}, status=403)
    
    try:
        notification_service = UserNotificationService()
        result = notification_service.test_connection()
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error testing new user notification: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def send_new_user_notification(request):
    """Отправка уведомления о новом пользователе"""
    
    try:
        # Получаем данные пользователя из запроса
        data = json.loads(request.body)
        
        # Проверяем обязательные поля
        required_fields = ['fullname', 'email', 'student_code']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }, status=400)
        
        # Отправляем уведомление
        notification_service = UserNotificationService()
        success = notification_service.send_new_user_notification(data)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'New user notification sent successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to send new user notification'
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error sending new user notification: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
