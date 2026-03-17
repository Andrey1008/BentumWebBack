import time
from datetime import datetime, timedelta
from django.utils import timezone
from .models import User, UserBan

class BanService:
    """Сервис для управления блокировками пользователей"""
    
    @staticmethod
    def ban_user(student_code, banned_by_id, duration_seconds, reason):
        """
        Заблокировать пользователя
        
        Args:
            student_code: Код студента
            banned_by_id: ID администратора
            duration_seconds: Длительность в секундах
            reason: Причина блокировки
        
        Returns:
            dict: Результат операции
        """
        try:
            # Получаем пользователя
            user = User.objects.get(student_code=student_code)
            
            # Проверяем что не забанен администратор
            if user.id == 1 or user.fullname.lower().startswith('admin'):
                return {
                    'success': False,
                    'detail': 'Нельзя забанить администратора'
                }
            
            # Деактивируем предыдущие баны
            UserBan.objects.filter(
                student_code=student_code,
                is_active=True
            ).update(is_active=False)
            
            # Создаем новую запись о бане
            ban = UserBan.objects.create(
                student_code=student_code,
                user_id=user.id,
                banned_by_id=banned_by_id,
                ban_duration_seconds=duration_seconds,
                ban_reason=reason,
                is_active=True
            )
            
            # Рассчитываем дату окончания бана
            ban_end_date = ban.ban_date + timedelta(seconds=duration_seconds)
            
            return {
                'success': True,
                'ban_id': ban.id,
                'ban_end_date': ban_end_date.isoformat(),
                'ban_duration_seconds': duration_seconds,
                'ban_reason': reason
            }
            
        except User.DoesNotExist:
            return {
                'success': False,
                'detail': 'Пользователь не найден'
            }
        except Exception as e:
            return {
                'success': False,
                'detail': f'Ошибка при разблокировке: {str(e)}'
            }
    
    @staticmethod
    def unban_user(student_code, unbanned_by_id, reason=''):
        """
        Разблокировать пользователя
        
        Args:
            student_code: Код студента
            unbanned_by_id: ID администратора
            reason: Причина разбана (не сохраняется)
        
        Returns:
            dict: Результат операции
        """
        try:
            # Получаем пользователя
            user = User.objects.get(student_code=student_code)
            
            # Деактивируем все активные баны
            active_bans = UserBan.objects.filter(
                student_code=student_code,
                is_active=True
            )
            
            if not active_bans.exists():
                return {
                    'success': False,
                    'detail': 'Пользователь не забанен'
                }
            
            # Деактивируем баны
            active_bans.update(is_active=False)
            
            return {
                'success': True,
                'message': 'Пользователь разблокирован'
            }
            
        except User.DoesNotExist:
            return {
                'success': False,
                'detail': 'Пользователь не найден'
            }
        except Exception as e:
            return {
                'success': False,
                'detail': f'Ошибка при разблокировке: {str(e)}'
            }
    
    @staticmethod
    def check_ban_status(student_code):
        """
        Проверить статус бана пользователя
        
        Args:
            student_code: Код студента
        
        Returns:
            dict: Информация о бане
        """
        try:
            # Получаем активный бан
            ban = UserBan.objects.filter(
                student_code=student_code,
                is_active=True
            ).first()
            
            if not ban:
                return {
                    'is_banned': False,
                    'ban_info': None
                }
            
            # Проверяем не истек ли бан
            current_time = timezone.now()
            ban_end_time = ban.ban_date + timedelta(seconds=ban.ban_duration_seconds)
            
            if current_time > ban_end_time:
                # Бан истек, деактивируем его
                ban.is_active = False
                ban.save()
                
                return {
                    'is_banned': False,
                    'ban_info': None
                }
            
            # Бан активен
            remaining_seconds = int((ban_end_time - current_time).total_seconds())
            
            return {
                'is_banned': True,
                'ban_info': {
                    'ban_id': ban.id,
                    'student_code': ban.student_code,
                    'user_id': ban.user_id,
                    'banned_by_id': ban.banned_by_id,
                    'ban_date': ban.ban_date.isoformat(),
                    'ban_end_date': ban_end_time.isoformat(),
                    'ban_duration_seconds': ban.ban_duration_seconds,
                    'remaining_seconds': remaining_seconds,
                    'ban_reason': ban.ban_reason
                }
            }
            
        except Exception as e:
            return {
                'is_banned': False,
                'error': str(e)
            }
    
    @staticmethod
    def get_all_bans(include_inactive=False):
        """
        Получить список всех банов
        
        Args:
            include_inactive: Включать неактивные баны
        
        Returns:
            list: Список банов
        """
        queryset = UserBan.objects.all()
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        bans = []
        for ban in queryset.select_related().order_by('-created_at'):
            ban_end_date = ban.ban_date + timedelta(seconds=ban.ban_duration_seconds)
            
            # Проверяем статус бана
            is_currently_active = ban.is_active and timezone.now() < ban_end_date
            
            bans.append({
                'id': ban.id,
                'student_code': ban.student_code,
                'user_id': ban.user_id,
                'banned_by_id': ban.banned_by_id,
                'ban_date': ban.ban_date.isoformat(),
                'ban_end_date': ban_end_date.isoformat(),
                'ban_duration_seconds': ban.ban_duration_seconds,
                'ban_reason': ban.ban_reason,
                'is_active': ban.is_active,
                'is_currently_active': is_currently_active,
                'created_at': ban.created_at.isoformat()
            })
        
        return bans
    
    @staticmethod
    def get_ban_statistics():
        """
        Получить статистику банов
        
        Returns:
            dict: Статистика
        """
        total_bans = UserBan.objects.count()
        active_bans = UserBan.objects.filter(is_active=True).count()
        
        # Считаем текущие активные баны (не истекшие)
        current_time = timezone.now()
        currently_active = 0
        
        for ban in UserBan.objects.filter(is_active=True):
            ban_end_time = ban.ban_date + timedelta(seconds=ban.ban_duration_seconds)
            if current_time < ban_end_time:
                currently_active += 1
        
        return {
            'total_bans': total_bans,
            'active_bans': active_bans,
            'currently_active': currently_active,
            'expired_bans': active_bans - currently_active
        }
