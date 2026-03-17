"""
Настройки хранения медиа файлов с оптимизацией места
"""

import os
from django.conf import settings
from django.core.files.storage import default_storage
from storages.backends.s3boto3 import S3Boto3Storage

class OptimizedStorage:
    """Класс для оптимизированного хранения"""
    
    @staticmethod
    def get_storage_path():
        """Получает путь для хранения медиа"""
        return os.path.join(settings.MEDIA_ROOT, 'users')
    
    @staticmethod
    def generate_unique_filename(original_filename, user_id, media_type):
        """Генерирует уникальное имя файла"""
        import uuid
        import hashlib
        from datetime import datetime
        
        # Хеш для дедупликации
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        name, ext = os.path.splitext(original_filename)
        return f"{user_id}/{media_type}/{timestamp}_{unique_id}{ext}"
    
    @staticmethod
    def get_disk_usage():
        """Получает информацию о использовании диска"""
        import shutil
        
        media_path = OptimizedStorage.get_storage_path()
        if os.path.exists(media_path):
            total, used, free = shutil.disk_usage(media_path)
            return {
                'total': total,
                'used': used,
                'free': free,
                'used_percent': (used / total) * 100
            }
        return None

# Настройки для production с S3
class S3OptimizedStorage(S3Boto3Storage):
    """S3 хранилище с оптимизацией"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self.custom_domain = settings.AWS_S3_CUSTOM_DOMAIN

# Конфигурация для разных окружений
STORAGE_CONFIG = {
    'development': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
        'OPTIONS': {
            'location': os.path.join(settings.BASE_DIR, 'media'),
            'base_url': '/media/',
        }
    },
    'production': {
        'BACKEND': 'backend.storage_settings.S3OptimizedStorage',
        'OPTIONS': {
            'bucket_name': settings.AWS_STORAGE_BUCKET_NAME,
            'access_key': settings.AWS_ACCESS_KEY_ID,
            'secret_key': settings.AWS_SECRET_ACCESS_KEY,
            'region': settings.AWS_S3_REGION,
            'custom_domain': settings.AWS_S3_CUSTOM_DOMAIN,
            'default_acl': 'private',
            'querystring_auth': True,
            'querystring_expire': 3600,  # 1 час
        }
    }
}

def get_storage_config():
    """Получает конфигурацию хранилища для текущего окружения"""
    env = getattr(settings, 'ENVIRONMENT', 'development')
    return STORAGE_CONFIG.get(env, STORAGE_CONFIG['development'])
