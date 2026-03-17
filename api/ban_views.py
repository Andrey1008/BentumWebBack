from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from .models import User, UserBan
from .ban_service import BanService

@api_view(['GET'])
def get_ban_info(request):
    """Получить информацию о бане текущего пользователя"""
    try:
        # Проверяем авторизацию
        if not request.session.get('is_authenticated'):
            return JsonResponse({"detail": "Требуется авторизация"}, status=401)
        
        # Получаем текущего пользователя
        try:
            student_code = request.session.get('student_code')
            if len(student_code) != 10 or not student_code.isdigit():
                return JsonResponse({"detail": "Некорректный код студента"}, status=400)
            user = User.objects.get(student_code=student_code)
        except User.DoesNotExist:
            return JsonResponse({"detail": "Пользователь не найден"}, status=404)
        
        # Получаем статус бана через BanService
        ban_status = BanService.check_ban_status(student_code)
        
        if not ban_status['is_banned']:
            return JsonResponse({
                "success": False,
                "detail": "Пользователь не забанен"
            }, status=404)
        
        ban_info = ban_status['ban_info']
        
        # Форматируем оставшееся время
        remaining_seconds = ban_info['remaining_seconds']
        days = remaining_seconds // (24 * 60 * 60)
        hours = (remaining_seconds % (24 * 60 * 60)) // (60 * 60)
        minutes = (remaining_seconds % (60 * 60)) // 60
        
        remaining_time_text = ""
        if days > 0:
            remaining_time_text += f"{days} дн. "
        if hours > 0:
            remaining_time_text += f"{hours} ч. "
        if minutes > 0:
            remaining_time_text += f"{minutes} мин."
        
        # Форматируем дату окончания
        from datetime import datetime
        end_date = datetime.fromisoformat(ban_info['ban_end_date'].replace('Z', '+00:00'))
        end_date_formatted = end_date.strftime('%d %B %Y года').replace('January', 'января').replace('February', 'февраля').replace('March', 'марта').replace('April', 'апреля').replace('May', 'мая').replace('June', 'июня').replace('July', 'июля').replace('August', 'августа').replace('September', 'сентября').replace('October', 'октября').replace('November', 'ноября').replace('December', 'декабря')
        
        # Форматируем длительность
        duration_seconds = ban_info['ban_duration_seconds']
        duration_days = duration_seconds // (24 * 60 * 60)
        
        if duration_days == 1:
            duration_text = "1 день"
        elif duration_days < 7:
            duration_text = f"{duration_days} дня"
        elif duration_days == 7:
            duration_text = "7 дней"
        elif duration_days < 30:
            duration_text = f"{duration_days} дней"
        elif duration_days == 30:
            duration_text = "30 дней"
        elif duration_days < 365:
            duration_text = f"{duration_days} дней"
        elif duration_days == 365:
            duration_text = "1 год"
        else:
            duration_text = f"{duration_days // 365} года"
        
        return JsonResponse({
            "success": True,
            "ban_info": {
                "reason": ban_info['ban_reason'],
                "duration_days": duration_days,
                "duration_text": duration_text,
                "end_date": ban_info['ban_end_date'],
                "end_date_formatted": end_date_formatted,
                "remaining_seconds": remaining_seconds,
                "remaining_time_text": remaining_time_text.strip(),
                "banned_by_id": ban_info['banned_by_id'],
                "ban_date": ban_info['ban_date']
            }
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "detail": f"Ошибка: {str(e)}"
        }, status=500)
