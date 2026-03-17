import os
import io
import hashlib
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.conf import settings
from django.core.files.storage import default_storage
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from .models import User, UserProfileMedia, MediaOptimization

class MediaOptimizer:
    """Класс для оптимизации изображений"""
    
    # Настройки оптимизации
    QUALITY_SETTINGS = {
        'thumbnail': {'quality': 70, 'max_size': (150, 150)},
        'small': {'quality': 75, 'max_size': (300, 300)},
        'medium': {'quality': 80, 'max_size': (800, 600)},
        'large': {'quality': 85, 'max_size': (1200, 800)},
    }
    
    SUPPORTED_FORMATS = {
        'image/jpeg': 'JPEG',
        'image/png': 'PNG',
        'image/webp': 'WEBP',
        'image/avif': 'AVIF',
    }
    
    @staticmethod
    def get_file_hash(content):
        """Генерирует хеш файла для дедупликации"""
        return hashlib.sha256(content).hexdigest()
    
    @staticmethod
    def optimize_image(image_content, output_format='WEBP', quality=80, max_size=(1200, 800)):
        """Оптимизирует изображение"""
        try:
            # Открываем изображение
            img = Image.open(io.BytesIO(image_content))
            
            # Конвертируем RGB если нужно
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Создаем миниатюру с сохранением пропорций
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Оптимизируем
            output = io.BytesIO()
            img.save(output, format=output_format, quality=quality, optimize=True)
            optimized_content = output.getvalue()
            
            return optimized_content
        except Exception as e:
            logger.error(f"Error optimizing image: {e}")
            return image_content
    
    @staticmethod
    def create_all_sizes(image_content, original_filename):
        """Создает все размеры изображения"""
        sizes = {}
        original_hash = MediaOptimizer.get_file_hash(image_content)
        
        for size_name, settings in MediaOptimizer.QUALITY_SETTINGS.items():
            try:
                optimized_content = MediaOptimizer.optimize_image(
                    image_content,
                    output_format='WEBP',
                    quality=settings['quality'],
                    max_size=settings['max_size']
                )
                
                # Генерируем имя файла
                base_name = os.path.splitext(original_filename)[0]
                optimized_filename = f"{original_hash}_{size_name}.webp"
                
                sizes[size_name] = {
                    'content': optimized_content,
                    'filename': optimized_filename,
                    'size': len(optimized_content),
                    'dimensions': settings['max_size']
                }
                
            except Exception as e:
                logger.error(f"Error creating {size_name} size: {e}")
                continue
        
        return sizes

class MediaStorage:
    """Класс для хранения медиа с дедупликацией"""
    
    @staticmethod
    def save_media(user, media_type, file_content, original_filename):
        """Сохраняет медиа с оптимизацией и дедупликацией"""
        try:
            # Проверяем MIME тип
            from django.core.files.uploadedfile import InMemoryUploadedFile
            import mimetypes
            
            mime_type = mimetypes.guess_type(original_filename)[0] or 'image/jpeg'
            
            # Получаем хеш файла
            file_hash = MediaOptimizer.get_file_hash(file_content)
            
            # Проверяем на дедупликацию (только для этого пользователя)
            existing_media = UserProfileMedia.objects.filter(
                user=user,
                file_path__contains=file_hash
            ).first()
            
            if existing_media:
                # Если найден дубликат, активируем его вместо создания нового
                if existing_media.media_type == media_type:
                    # Деактивируем другие медиа этого типа
                    UserProfileMedia.objects.filter(
                        user=user,
                        media_type=media_type,
                        is_active=True
                    ).update(is_active=False)
                    
                    existing_media.is_active = True
                    existing_media.save()
                    
                    # Очищаем старые медиа
                    MediaStorage.cleanup_old_media(user, media_type)
                    
                    return existing_media
                else:
                    # Если другой тип медиа, создаем новый файл с другим хешом
                    pass
            
            # Создаем оптимизированные версии
            sizes = MediaOptimizer.create_all_sizes(file_content, original_filename)
            
            # Сохраняем файлы
            base_path = f"users/{user.student_code}/{media_type}s"
            
            # Оригинал (оптимизированный)
            original_path = f"{base_path}/{file_hash}_original.webp"
            default_storage.save(original_path, ContentFile(sizes['large']['content']))
            
            # Сохраняем миниатюры
            for size_name, size_data in sizes.items():
                if size_name != 'large':
                    path = f"{base_path}/{size_data['filename']}"
                    default_storage.save(path, ContentFile(size_data['content']))
            
            # Получаем размеры изображения
            img = Image.open(io.BytesIO(file_content))
            width, height = img.size
            
            # Создаем запись в БД
            media = UserProfileMedia.objects.create(
                user=user,
                media_type=media_type,
                original_filename=original_filename,
                file_path=original_path,
                file_size=len(file_content),
                mime_type=mime_type,
                width=width,
                height=height,
                is_active=False  # Неактивен до подтверждения
            )
            
            # Сохраняем оптимизированные версии
            for size_name, size_data in sizes.items():
                MediaOptimization.objects.create(
                    original_media=media,
                    size_type=size_name,
                    file_path=f"{base_path}/{size_data['filename']}",
                    file_size=size_data['size']
                )
            
            return media
            
        except Exception as e:
            import traceback
            logger.error(f"Error in save_media: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error(f"User: {user.student_code}, Media type: {media_type}, Filename: {original_filename}")
            raise

    @staticmethod
    def get_media_url(media, size='medium'):
        """Получает URL медиа с нужным размером"""
        try:
            if not media:
                return None
            
            # Ищем оптимизированную версию
            optimization = MediaOptimization.objects.filter(
                original_media=media,
                size_type=size
            ).first()
            
            if optimization and default_storage.exists(optimization.file_path):
                return default_storage.url(optimization.file_path)
            
            # Возвращаем оригинал если нет оптимизации
            if default_storage.exists(media.file_path):
                return default_storage.url(media.file_path)
            
            # Если файла нет, возвращаем плейсхолдер
            from .placeholder_service import PlaceholderGenerator
            placeholder = PlaceholderGenerator.get_or_create_placeholder(media.user, media.media_type)
            if placeholder and default_storage.exists(placeholder.file_path):
                return default_storage.url(placeholder.file_path)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting media URL: {e}")
            return None
    
    @staticmethod
    def get_placeholder_data(user, media_type):
        """Возвращает данные для CSS плейсхолдера"""
        try:
            from .placeholder_service import PlaceholderGenerator
            
            if media_type == 'avatar':
                return PlaceholderGenerator.get_avatar_placeholder_data(user.fullname)
            elif media_type == 'banner':
                return PlaceholderGenerator.get_banner_placeholder_data()
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting placeholder data: {e}")
            return None

    @staticmethod
    def delete_media_files(media):
        """Полностью удаляет файлы медиа и запись из БД"""
        try:
            # Удаляем основной файл
            if default_storage.exists(media.file_path):
                default_storage.delete(media.file_path)
            
            # Удаляем оптимизированные версии
            for opt in media.optimized_versions.all():
                if default_storage.exists(opt.file_path):
                    default_storage.delete(opt.file_path)
                opt.delete()
            
            # Удаляем запись из БД
            media.delete()
            logger.info(f"Deleted media files: {media.id}")
            
        except Exception as e:
            logger.error(f"Error deleting media {media.id}: {e}")

    @staticmethod
    def cleanup_old_media(user, media_type):
        """Удаляет старые медиа указанного типа для пользователя"""
        try:
            # Находим все старые медиа этого типа (кроме активных)
            old_media = UserProfileMedia.objects.filter(
                user=user,
                media_type=media_type,
                is_active=False
            )
            
            deleted_count = 0
            for media in old_media:
                try:
                    MediaStorage.delete_media_files(media)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting old media {media.id}: {e}")
                    continue
                
            logger.info(f"Cleaned up {deleted_count} old {media_type}s for user {user.student_code}")
            
        except Exception as e:
            logger.error(f"Error in cleanup_old_media: {e}")
            # Не прерываем процесс загрузки если очистка не удалась

    @staticmethod
    def cleanup_all_old_media():
        """Очистка старых неиспользуемых медиа"""
        cutoff_date = datetime.now() - timedelta(days=30)
        
        # Находим старые неактивные медиа
        old_media = UserProfileMedia.objects.filter(
            created_at__lt=cutoff_date,
            is_active=False
        )
        
        for media in old_media:
            try:
                # Удаляем файлы
                if default_storage.exists(media.file_path):
                    default_storage.delete(media.file_path)
                
                # Удаляем оптимизированные версии
                for opt in media.optimized_versions.all():
                    if default_storage.exists(opt.file_path):
                        default_storage.delete(opt.file_path)
                
                # Удаляем записи из БД
                media.delete()
                logger.info(f"Cleaned up old media: {media.id}")
                
            except Exception as e:
                logger.error(f"Error cleaning up media {media.id}: {e}")

class MediaValidator:
    """Валидатор медиа файлов"""
    
    ALLOWED_MIME_TYPES = [
        'image/jpeg',
        'image/png', 
        'image/webp',
        'image/avif'
    ]
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_DIMENSIONS = (4000, 4000)  # Максимальный размер
    
    @staticmethod
    def validate_image(file_content, filename):
        """Валидирует изображение"""
        errors = []
        
        # Проверяем MIME тип
        import mimetypes
        mime_type = mimetypes.guess_type(filename)[0]
        
        if mime_type not in MediaValidator.ALLOWED_MIME_TYPES:
            errors.append(f"Неподдерживаемый формат: {mime_type}")
        
        # Проверяем размер файла
        if len(file_content) > MediaValidator.MAX_FILE_SIZE:
            errors.append(f"Файл слишком большой: {len(file_content) / 1024 / 1024:.1f}MB")
        
        # Проверяем размеры изображения
        try:
            img = Image.open(io.BytesIO(file_content))
            if img.size[0] > MediaValidator.MAX_DIMENSIONS[0] or \
               img.size[1] > MediaValidator.MAX_DIMENSIONS[1]:
                errors.append(f"Изображение слишком большое: {img.size}")
        except Exception as e:
            errors.append(f"Невозможно прочитать изображение: {e}")
        
        return errors
