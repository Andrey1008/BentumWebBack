from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view
from .models import User
from .ban_service import BanService
from django.utils import timezone
import json
import re
from datetime import datetime, timedelta
from django.conf import settings

@api_view(['GET'])
def get_all_users(request):
    """Получить всех пользователей для админки"""
    try:
        # Проверяем что пользователь админ (ID = 1)
        if not request.session.get('is_authenticated'):
            return JsonResponse({"detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что это админ
        if current_user.id != 1:
            return JsonResponse({"detail": "Доступ запрещен"}, status=403)
        
        # Получаем всех пользователей
        users = User.objects.all().order_by('-created_at')
        
        users_data = []
        for user in users:
            # Проверяем статус бана через BanService
            ban_status = BanService.check_ban_status(user.student_code)
            
            users_data.append({
                'id': user.id,
                'fullname': user.fullname,
                'faculty': user.faculty,
                'student_code': user.student_code,
                'registration_date': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None,
                'last_login_ip': user.last_login_ip,
                'status': 'banned' if ban_status['is_banned'] else 'active',
                'avatar_url': None,  # Будет добавлено позже
                'ban_reason': ban_status['ban_info']['ban_reason'] if ban_status['is_banned'] and ban_status['ban_info'] else None,
                'ban_end_date': ban_status['ban_info']['ban_end_date'] if ban_status['is_banned'] and ban_status['ban_info'] else None,
                'is_banned': ban_status['is_banned']
            })
        
        return JsonResponse({
            "success": True,
            "users": users_data
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "detail": f"Ошибка: {str(e)}"
        }, status=500)

@api_view(['GET'])
def get_users_stats(request):
    """Получить статистику пользователей"""
    try:
        # Проверяем что пользователь админ (ID = 1)
        if not request.session.get('is_authenticated'):
            return JsonResponse({"detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что это админ
        if current_user.id != 1:
            return JsonResponse({"detail": "Доступ запрещен"}, status=403)
        
        total_users = User.objects.count()
        
        # Получаем статистику банов через BanService
        ban_stats = BanService.get_ban_statistics()
        banned_users = ban_stats['currently_active']
        active_users = total_users - banned_users
        
        # Новые пользователи сегодня
        today = timezone.now().date()
        new_users_today = User.objects.filter(created_at__date=today).count()
        
        return JsonResponse({
            "success": True,
            "stats": {
                "totalUsers": total_users,
                "bannedUsers": banned_users,
                "activeUsers": active_users,
                "newUsersToday": new_users_today
            }
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "detail": f"Ошибка: {str(e)}"
        }, status=500)

@api_view(['POST'])
def create_user(request):
    """Создать нового пользователя"""
    try:
        # Проверяем что пользователь админ (ID = 1)
        if not request.session.get('is_authenticated'):
            return JsonResponse({"detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что это админ
        if current_user.id != 1:
            return JsonResponse({"detail": "Доступ запрещен"}, status=403)
        
        data = json.loads(request.body)
        
        # Валидация
        required_fields = ['fullname', 'student_code', 'faculty']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False,
                    'detail': f'Поле {field} обязательно для заполнения'
                }, status=400)
        
        # Проверка формата кода студента
        if not re.match(r'^\d{8}$', data['student_code']):
            return JsonResponse({
                'success': False,
                'detail': 'Код студента должен состоять из 8 цифр'
            }, status=400)
        
        # Проверка на дубликаты
        if User.objects.filter(student_code=data['student_code']).exists():
            return JsonResponse({
                'success': False,
                'detail': 'Пользователь с таким кодом студента уже существует'
            }, status=400)
        
        # Создаем пользователя
        user = User.objects.create(
            fullname=data['fullname'],
            student_code=data['student_code'],
            faculty=data['faculty'],
            bilet_code='0000000'  # Пароль по умолчанию
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Пользователь {data["fullname"]} успешно создан'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'detail': f"Ошибка: {str(e)}"
        }, status=500)

@api_view(['POST'])
def ban_user(request):
    """Забанить пользователя"""
    try:
        # Проверяем что пользователь админ (ID = 1)
        if not request.session.get('is_authenticated'):
            return JsonResponse({"detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что это админ
        if current_user.id != 1:
            return JsonResponse({"detail": "Доступ запрещен"}, status=403)
        
        data = json.loads(request.body)
        user_id = data.get('user_id')
        reason = data.get('reason', 'Причина не указана')
        duration_days = data.get('duration', 7)
        
        if not user_id:
            return JsonResponse({
                'success': False,
                'detail': 'ID пользователя обязателен'
            }, status=400)
        
        # Получаем студенческий код пользователя
        try:
            user_to_ban = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({
                'success': False,
                'detail': 'Пользователь не найден'
            }, status=404)
        
        # Конвертируем дни в секунды
        duration_seconds = duration_days * 24 * 60 * 60
        
        # Используем BanService для бана
        result = BanService.ban_user(
            student_code=user_to_ban.student_code,
            banned_by_id=current_user.id,
            duration_seconds=duration_seconds,
            reason=reason
        )
        
        if result['success']:
            return JsonResponse({
                'success': True,
                'message': f'Пользователь {user_to_ban.fullname} заблокирован',
                'ban_end_date': result.get('ban_end_date'),
                'ban_duration_seconds': result.get('ban_duration_seconds'),
                'ban_reason': result.get('ban_reason')
            })
        else:
            return JsonResponse({
                'success': False,
                'detail': result['detail']
            }, status=400)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'detail': f"Ошибка: {str(e)}"
        }, status=500)

@api_view(['POST'])
def unban_user(request):
    """Разбанить пользователя"""
    try:
        # Проверяем что пользователь админ (ID = 1)
        if not request.session.get('is_authenticated'):
            return JsonResponse({"detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что это админ
        if current_user.id != 1:
            return JsonResponse({"detail": "Доступ запрещен"}, status=403)
        
        data = json.loads(request.body)
        user_id = data.get('user_id')
        
        if not user_id:
            return JsonResponse({
                'success': False,
                'detail': 'ID пользователя обязателен'
            }, status=400)
        
        # Получаем студенческий код пользователя
        try:
            user_to_unban = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({
                'success': False,
                'detail': 'Пользователь не найден'
            }, status=404)
        
        # Используем BanService для разбана
        from .ban_service import BanService
        result = BanService.unban_user(
            student_code=user_to_unban.student_code,
            unbanned_by_id=current_user.id
        )
        
        if result['success']:
            return JsonResponse({
                'success': True,
                'message': f'Пользователь {user_to_unban.fullname} разблокирован'
            })
        else:
            return JsonResponse({
                'success': False,
                'detail': result['detail']
            }, status=400)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'detail': f"Ошибка: {str(e)}"
        }, status=500)
