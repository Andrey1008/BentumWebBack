import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.db import transaction
from django.core.paginator import Paginator
from datetime import datetime

from .models import User, Administration
from .func import authorize
from .ban_service import BanService

@csrf_exempt
@require_http_methods(["POST"])
def appoint_administrator(request):
    """Назначение администратора"""
    try:
        # Проверка авторизации и прав
        session_key = request.session.session_key
        if not session_key:
            return JsonResponse({"success": False, "detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"success": False, "detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что текущий пользователь - администратор
        if not Administration.objects.filter(administrator=current_user, is_active=True).exists():
            return JsonResponse({"success": False, "detail": "Недостаточно прав"}, status=403)
        
        # Получаем данные запроса
        data = json.loads(request.body)
        target_student_code = data.get('student_code')
        notes = data.get('notes', '')
        
        if not target_student_code:
            return JsonResponse({"success": False, "detail": "Не указан код студента"}, status=400)
        
        # Находим целевого пользователя
        try:
            target_user = User.objects.get(student_code=target_student_code)
        except User.DoesNotExist:
            return JsonResponse({"success": False, "detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что пользователь еще не администратор
        if Administration.objects.filter(administrator=target_user, is_active=True).exists():
            return JsonResponse({"success": False, "detail": "Пользователь уже является администратором"}, status=400)
        
        # Создаем запись о назначении
        with transaction.atomic():
            admin_record = Administration.objects.create(
                administrator=target_user,
                appointed_by=current_user,
                notes=notes
            )
        
        return JsonResponse({
            "success": True,
            "message": f"Пользователь {target_user.fullname} назначен администратором",
            "administration": {
                "id": admin_record.id,
                "administrator": {
                    "id": target_user.id,
                    "student_code": target_user.student_code,
                    "fullname": target_user.fullname,
                    "faculty": target_user.faculty
                },
                "appointed_by": {
                    "id": current_user.id,
                    "student_code": current_user.student_code,
                    "fullname": current_user.fullname
                },
                "appointed_at": admin_record.appointed_at.isoformat(),
                "notes": admin_record.notes
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "detail": "Неверный формат данных"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "detail": f"Ошибка сервера: {str(e)}"}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def remove_administrator(request):
    """Снятие администратора"""
    try:
        # Проверка авторизации и прав
        session_key = request.session.session_key
        if not session_key:
            return JsonResponse({"success": False, "detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"success": False, "detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что текущий пользователь - администратор
        if not Administration.objects.filter(administrator=current_user, is_active=True).exists():
            return JsonResponse({"success": False, "detail": "Недостаточно прав"}, status=403)
        
        # Получаем данные запроса
        data = json.loads(request.body)
        target_student_code = data.get('student_code')
        
        if not target_student_code:
            return JsonResponse({"success": False, "detail": "Не указан код студента"}, status=400)
        
        # Находим целевого пользователя
        try:
            target_user = User.objects.get(student_code=target_student_code)
        except User.DoesNotExist:
            return JsonResponse({"success": False, "detail": "Пользователь не найден"}, status=404)
        
        # Находим и деактивируем запись администратора
        try:
            admin_record = Administration.objects.get(administrator=target_user, is_active=True)
            admin_record.is_active = False
            admin_record.save()
        except Administration.DoesNotExist:
            return JsonResponse({"success": False, "detail": "Пользователь не является администратором"}, status=400)
        
        return JsonResponse({
            "success": True,
            "message": f"Пользователь {target_user.fullname} снят с должности администратора"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "detail": "Неверный формат данных"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "detail": f"Ошибка сервера: {str(e)}"}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_administrators(request):
    """Получение списка администраторов"""
    try:
        # Проверка авторизации и прав
        session_key = request.session.session_key
        if not session_key:
            return JsonResponse({"success": False, "detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"success": False, "detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что текущий пользователь - администратор
        if not Administration.objects.filter(administrator=current_user, is_active=True).exists():
            return JsonResponse({"success": False, "detail": "Недостаточно прав"}, status=403)
        
        # Получаем параметры пагинации
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        # Получаем активных администраторов
        admin_records = Administration.objects.filter(is_active=True).select_related(
            'administrator', 'appointed_by'
        ).order_by('-appointed_at')
        
        # Пагинация
        paginator = Paginator(admin_records, per_page)
        page_obj = paginator.get_page(page)
        
        administrators = []
        for record in page_obj:
            # Проверяем статус бана через BanService
            ban_status = BanService.check_ban_status(record.administrator.student_code)
            
            administrators.append({
                "id": record.id,
                "administrator": {
                    "id": record.administrator.id,
                    "student_code": record.administrator.student_code,
                    "fullname": record.administrator.fullname,
                    "faculty": record.administrator.faculty,
                    "created_at": record.administrator.created_at.isoformat(),
                    "last_login": record.administrator.last_login.isoformat() if record.administrator.last_login else None,
                    "is_banned": ban_status['is_banned']
                },
                "appointed_by": {
                    "id": record.appointed_by.id,
                    "student_code": record.appointed_by.student_code,
                    "fullname": record.appointed_by.fullname
                } if record.appointed_by else None,
                "appointed_at": record.appointed_at.isoformat(),
                "notes": record.notes
            })
        
        return JsonResponse({
            "success": True,
            "administrators": administrators,
            "pagination": {
                "current_page": page,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
                "per_page": per_page,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous()
            }
        })
        
    except Exception as e:
        return JsonResponse({"success": False, "detail": f"Ошибка сервера: {str(e)}"}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_administration_history(request):
    """Получение истории назначений администраторов"""
    try:
        # Проверка авторизации и прав
        session_key = request.session.session_key
        if not session_key:
            return JsonResponse({"success": False, "detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            current_user = User.objects.get(student_code=request.session.get('student_code'))
        except User.DoesNotExist:
            return JsonResponse({"success": False, "detail": "Пользователь не найден"}, status=404)
        
        # Проверяем что текущий пользователь - администратор
        if not Administration.objects.filter(administrator=current_user, is_active=True).exists():
            return JsonResponse({"success": False, "detail": "Недостаточно прав"}, status=403)
        
        # Получаем параметры
        target_student_code = request.GET.get('student_code')
        
        # Фильтруем записи
        if target_student_code:
            try:
                target_user = User.objects.get(student_code=target_student_code)
                records = Administration.objects.filter(
                    administrator=target_user
                ).select_related('appointed_by').order_by('-appointed_at')
            except User.DoesNotExist:
                return JsonResponse({"success": False, "detail": "Пользователь не найден"}, status=404)
        else:
            records = Administration.objects.all().select_related(
                'administrator', 'appointed_by'
            ).order_by('-appointed_at')
        
        # Формируем историю
        history = []
        for record in records:
            history.append({
                "id": record.id,
                "administrator": {
                    "id": record.administrator.id,
                    "student_code": record.administrator.student_code,
                    "fullname": record.administrator.fullname
                },
                "appointed_by": {
                    "id": record.appointed_by.id,
                    "student_code": record.appointed_by.student_code,
                    "fullname": record.appointed_by.fullname
                } if record.appointed_by else None,
                "appointed_at": record.appointed_at.isoformat(),
                "is_active": record.is_active,
                "notes": record.notes
            })
        
        return JsonResponse({
            "success": True,
            "history": history,
            "total": len(history)
        })
        
    except Exception as e:
        return JsonResponse({"success": False, "detail": f"Ошибка сервера: {str(e)}"}, status=500)
