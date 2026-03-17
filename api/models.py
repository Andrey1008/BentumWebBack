from django.db import models

class User(models.Model):
    fullname = models.CharField(max_length=100)
    faculty = models.CharField(max_length=10)
    student_code = models.CharField(max_length=10, unique=True)
    bilet_code = models.CharField(max_length=7)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.student_code


class UserSession(models.Model):
    student_code = models.CharField(max_length=10, db_index=True)
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_sessions'
        indexes = [
            models.Index(fields=['student_code', 'created_at']),
        ]


# Модели для медиа файлов
class UserProfileMedia(models.Model):
    """Модель для хранения медиа файлов пользователей"""
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='media_files')
    media_type = models.CharField(max_length=10, choices=[
        ('avatar', 'Аватар'),
        ('banner', 'Баннер'),
    ])
    original_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.IntegerField()  # в байтах
    mime_type = models.CharField(max_length=100)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=False)  # Текущий активный медиа
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_profile_media'
        indexes = [
            models.Index(fields=['user', 'media_type', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.student_code} - {self.media_type}"


class MediaOptimization(models.Model):
    """Модель для хранения оптимизированных версий изображений"""
    original_media = models.ForeignKey('UserProfileMedia', on_delete=models.CASCADE, related_name='optimized_versions')
    size_type = models.CharField(max_length=20, choices=[
        ('thumbnail', 'Миниатюра 150x150'),
        ('small', 'Маленький 300x300'),
        ('medium', 'Средний 800x600'),
        ('large', 'Большой 1200x800'),
    ])
    file_path = models.CharField(max_length=500)
    file_size = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'media_optimizations'
        indexes = [
            models.Index(fields=['original_media', 'size_type']),
        ]


class Administration(models.Model):
    """Модель для отслеживания администраторов системы"""
    administrator = models.ForeignKey('User', on_delete=models.CASCADE, related_name='admin_assignments')
    appointed_by = models.ForeignKey('User', on_delete=models.CASCADE, related_name='appointed_admins', null=True, blank=True)
    appointed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text="Примечания о назначении")
    
    class Meta:
        db_table = 'administration'
        indexes = [
            models.Index(fields=['administrator', 'is_active']),
            models.Index(fields=['appointed_by']),
            models.Index(fields=['appointed_at']),
        ]
    
    def __str__(self):
        return f"Admin: {self.administrator.student_code} (назначен {self.appointed_at.strftime('%d.%m.%Y')})"


class UserBan(models.Model):
    """Модель для хранения информации о блокировках пользователей"""
    student_code = models.CharField(max_length=10, db_index=True)
    user_id = models.IntegerField(db_index=True)
    banned_by_id = models.IntegerField(null=True, blank=True)  # ID администратора
    ban_date = models.DateTimeField(auto_now_add=True)
    ban_duration_seconds = models.IntegerField()  # Длительность в Unix секундах
    ban_reason = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_bans'
        indexes = [
            models.Index(fields=['student_code', 'is_active']),
            models.Index(fields=['user_id', 'is_active']),
            models.Index(fields=['banned_by_id']),
            models.Index(fields=['ban_date']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Ban: {self.student_code} (by {self.banned_by_id}) - {self.ban_duration_seconds}s"