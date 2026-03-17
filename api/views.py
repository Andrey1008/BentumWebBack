import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .func import authorize
import pytz
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore
from django.conf import settings
from django.core.cache import cache

from .models import User, UserSession
from .func import authorize
from .user_notification_service import UserNotificationService
from .ban_service import BanService


SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _check_login_attempts(student_code: str, ip_address: str) -> tuple[bool, str]:
    """Проверяет количество попыток входа для защиты от подбора пароля"""
    
    # Ключи для кэша
    user_key = f"login_attempts_user:{student_code}"
    ip_key = f"login_attempts_ip:{ip_address}"
    
    # Получаем текущие счетчики
    user_attempts = cache.get(user_key, 0)
    ip_attempts = cache.get(ip_key, 0)
    
    # Проверяем лимиты
    if user_attempts >= 5:
        return False, "Слишком много попыток входа. Попробуйте позже."
    
    if ip_attempts >= 10:
        return False, "Слишком много попыток входа с этого IP. Попробуйте позже."
    
    # Увеличиваем счетчики
    cache.set(user_key, user_attempts + 1, 15)  # 15 секунд
    cache.set(ip_key, ip_attempts + 1, 15)      # 15 секунд
    
    return True, ""


def _clear_login_attempts(student_code: str, ip_address: str):
    """Сбрасывает счетчики попыток входа после успешной авторизации"""
    cache.delete(f"login_attempts_user:{student_code}")
    cache.delete(f"login_attempts_ip:{ip_address}")


def _enforce_session_limits(student_code: str, current_session_key: str) -> None:
    if not student_code or not current_session_key:
        return

    UserSession.objects.get_or_create(
        session_key=current_session_key,
        defaults={"student_code": student_code},
    )

    sessions = list(
        UserSession.objects.filter(student_code=student_code).order_by('-created_at')
    )
    if len(sessions) <= 2:
        return

    for s in sessions[2:]:
        Session.objects.filter(session_key=s.session_key).delete()
        s.delete()


@csrf_exempt
def save_data(request):
    if request.method != "POST":
        return JsonResponse(
            {"detail": "Метод не разрешён"},
            status=405
        )


    try:
        if isinstance(request.body, bytes):
            body_str = request.body.decode('utf-8')
        else:
            body_str = request.body
        
        data = json.loads(body_str)
        student_code = data.get("studentCode")
        red_code = data.get("studentRedCode")

        if not student_code or not red_code:
            return JsonResponse(
                {"detail": "Отсутствуют обязательные поля"},
                status=400
            )

        if len(student_code) != 10 or len(red_code) != 7:
            return JsonResponse(
                {"detail": "Некорректный формат кодов"},
                status=400
            )

        # Получаем IP адрес для проверки попыток входа
        ip_address = request.META.get('REMOTE_ADDR', 'unknown')
        
        # Проверяем количество попыток входа
        can_login, error_message = _check_login_attempts(student_code, ip_address)
        if not can_login:
            return JsonResponse(
                {"detail": error_message},
                status=429  # Too Many Requests
            )

        existing_user = User.objects.filter(student_code=student_code).first()
        if existing_user:
            # Проверяем пароль (bilet_code) для существующего пользователя
            if existing_user.bilet_code != red_code:
                return JsonResponse(
                    {"detail": "Неверный пароль"},
                    status=401
                )
            
            # Сбрасываем счетчики попыток после успешного входа
            _clear_login_attempts(student_code, ip_address)
            
            # Обновляем время входа и IP
            existing_user.last_login = datetime.now(pytz.UTC)
            existing_user.last_login_ip = ip_address
            existing_user.save()
            
            request.session['student_code'] = existing_user.student_code
            request.session['fullname'] = existing_user.fullname
            request.session['faculty'] = existing_user.faculty
            request.session['is_authenticated'] = True

            request.session.set_expiry(SESSION_MAX_AGE_SECONDS)
            
            request.session.save()

            _enforce_session_limits(existing_user.student_code, request.session.session_key)
            
            # Проверяем статус бана через BanService
            ban_status = BanService.check_ban_status(existing_user.student_code)
            
            return JsonResponse({
                "success": True,
                "message": "Вход выполнен успешно",
                "user": {
                    "id": existing_user.id,
                    "fullname": existing_user.fullname,
                    "student_code": existing_user.student_code,
                    "faculty": existing_user.faculty,
                    "is_banned": ban_status['is_banned']
                }
            }, status=200)

        auth_result = authorize(student_code, red_code)
        
        if auth_result is False:
            return JsonResponse(
                {"detail": "Неверные данные авторизации"},
                status=401
            )
        
        # Сбрасываем счетчики попыток после успешной авторизации
        _clear_login_attempts(student_code, ip_address)
        
        fullname, faculty = auth_result
        
        user = User.objects.create(
            fullname=fullname,
            faculty=faculty,
            student_code=student_code,
            bilet_code=red_code,
            created_at=datetime.now(pytz.UTC)
        )
        
        # Сбрасываем счетчики попыток после успешной регистрации
        _clear_login_attempts(student_code, ip_address)
        
        # Отправляем уведомление о новом пользователе в Telegram
        try:
            notification_service = UserNotificationService()
            user_data = {
                'id': user.id,
                'fullname': user.fullname,
                'student_code': user.student_code,
                'faculty': user.faculty
            }
            notification_service.send_new_user_notification(user_data)
        except Exception as e:
            # Не прерываем процесс авторизации если уведомление не отправилось
            pass
                
        request.session['student_code'] = user.student_code
        request.session['fullname'] = user.fullname
        request.session['faculty'] = user.faculty
        request.session['is_authenticated'] = True

        request.session.set_expiry(SESSION_MAX_AGE_SECONDS)
        
        request.session.save()

        _enforce_session_limits(user.student_code, request.session.session_key)
        
        
        response_data = {
            "success": True,
            "message": "Регистрация прошла успешно",
            "redirect": f"/api/dashboard?student_code={user.student_code}",
            "user": {
                "id": user.id,
                "fullname": user.fullname,
                "faculty": user.faculty,
                "student_code": user.student_code,
                "created_at": user.created_at.isoformat()
            }
        }
        
        response = HttpResponse(
            json.dumps(response_data),
            content_type='application/json',
            status=200
        )
        
        response.set_cookie(
            'sessionid',
            request.session.session_key,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite='Lax',
            secure=False,
            path='/',
        )
        
        return response

    except json.JSONDecodeError:
        return JsonResponse(
            {"detail": "Некорректный JSON"},
            status=400
        )

    except Exception as e:
        return JsonResponse(
            {"detail": f"Ошибка сервера: {e}"},
            status=500
        )


@csrf_exempt
def dashboard(request):
    """
    Личный кабинет пользователя
    """
    if request.method != "GET":
        return JsonResponse(
            {"detail": "Метод не разрешён"},
            status=405
        )
    
    student_code = request.GET.get('student_code')
    
    
    if not student_code:
        student_code = request.session.get('student_code')
    
    if not request.session.get('is_authenticated') or not student_code:
        return JsonResponse(
            {"detail": "Пользователь не авторизован"},
            status=401
        )
    
    try:
        user = User.objects.get(student_code=student_code)
        
        session_student_code = request.session.get('student_code')
        if session_student_code != student_code:
            return JsonResponse(
                {"detail": "Доступ запрещён"},
                status=403
            )
        
        # Проверяем статус бана через BanService
        ban_status = BanService.check_ban_status(student_code)
        
        return JsonResponse({
            "success": True,
            "theme": request.session.get('theme', 'dark'),
            "user": {
                "id": user.id,
                "fullname": user.fullname,
                "faculty": user.faculty,
                "student_code": user.student_code,
                "created_at": user.created_at.isoformat(),
                "is_banned": ban_status['is_banned'],
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "last_login_ip": user.last_login_ip
            }
        }, status=200)
    
    except User.DoesNotExist:
        return JsonResponse(
            {"detail": "Пользователь не найден"},
            status=404
        )
    
    except Exception as e:
        return JsonResponse(
            {"detail": "Ошибка при работе с базой данных"},
            status=500
        )


@csrf_exempt
def logout(request):
    """
    Выход из системы - очистка сессии
    """
    try:
        session_key = request.session.session_key
        request.session.flush()

        if session_key:
            UserSession.objects.filter(session_key=session_key).delete()
        return JsonResponse({
            "success": True,
            "message": "Выход выполнен успешно"
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            "success": False,
            "detail": "Ошибка при выходе из системы"
        }, status=500)


@csrf_exempt
def theme(request):
    if request.method == "GET":
        return JsonResponse({
            "success": True,
            "theme": request.session.get('theme', 'dark')
        }, status=200)

    if request.method != "POST":
        return JsonResponse(
            {"detail": "Метод не разрешён"},
            status=405
        )

    try:
        data = json.loads(request.body)
        selected_theme = data.get('theme')
        if selected_theme not in ("dark", "light"):
            return JsonResponse(
                {"detail": "Некорректная тема"},
                status=400
            )


        request.session['theme'] = selected_theme
        request.session.modified = True
        request.session.save()


        return JsonResponse({
            "success": True,
            "theme": selected_theme
        }, status=200)
    except json.JSONDecodeError:
        return JsonResponse(
            {"detail": "Некорректный JSON"},
            status=400
        )


@csrf_exempt
def get_schedule(request):
    """Получение расписания для группы пользователя"""
    if request.method != "GET":
        return JsonResponse(
            {"detail": "Метод не разрешён"},
            status=405
        )
    
    
    if not request.session.get('is_authenticated'):
        return JsonResponse(
            {"detail": "Требуется авторизация"},
            status=401
        )
    
    student_code = request.session.get('student_code')
    if not student_code:
        return JsonResponse(
            {"detail": "Отсутствует код студента"},
            status=400
        )
    
    try:
        db_path = os.path.join(settings.BASE_DIR, 'schedules', 'schedules.db')
        
        if not os.path.exists(db_path):
            return JsonResponse(
                {"detail": "База данных расписаний не найдена"},
                status=404
            )
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        group_id = student_code[:8]
        
        cursor.execute("""
            SELECT day, week, time, matter, frame, teacher, classroom 
            FROM schedules 
            WHERE group_number = ? 
            ORDER BY day, week, time
        """, (group_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return JsonResponse(
                {"detail": f"Расписание для группы {group_id} не найдено"},
                status=404
            )
        
        schedule_data = {}
        
        for row in rows:
            day, week, time, matter, frame, teacher, classroom = row
            
            if day not in schedule_data:
                schedule_data[day] = {}
            week_type = 'upper' if week == 1 else 'lower'
            if week_type not in schedule_data[day]:
                schedule_data[day][week_type] = []
            
            schedule_data[day][week_type].append({
                "time": time,
                "subject": matter,
                "type": frame,
                "teacher": teacher,
                "classroom": classroom
            })
        
        return JsonResponse({
            "success": True,
            "schedule": schedule_data,
            "student_code": student_code
        }, status=200)
        
    except sqlite3.Error as e:
        return JsonResponse(
            {"detail": "Ошибка базы данных расписаний"},
            status=500
        )
    except Exception as e:
        return JsonResponse(
            {"detail": f"Внутренняя ошибка сервера: {str(e)}"},
            status=500
        )


@csrf_exempt
def get_literature(request):
    """Возвращает список литературы с пагинацией и фильтрацией.

    Параметры GET:
      - page (int) - номер страницы, начиная с 1 (по умолчанию 1)
      - page_size (int) - элементов на страницу (по умолчанию 6)
      - search (str) - поисковая строка по title/author/description
      - category (str) - id категории (например, "mathematics"), "all" или отсутствие означает без фильтра
    """
    if request.method != "GET":
        return JsonResponse({"detail": "Метод не разрешён"}, status=405)

    def _format_size(size: any) -> any:
        """Нормализует строку размера: округляет число до 2 знаков и стандартизует единицу (B/KB/MB/GB).
        Если формат нераспознан — возвращает исходное значение.
        Примеры: '1.763Mb' -> '1.76MB', '1763Kb' -> '1763.00KB' (если в данных такое встречается).
        """
        if not size and size != 0:
            return None

        if isinstance(size, (int, float)):
            try:
                return f"{float(size):.2f}"
            except Exception:
                return str(size)

        s = str(size).strip()
        s = re.sub(r'([0-9]+)\.([kKmMgGtT]?)\s*([bB])', r'\1\2\3', s)
        m = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([kKmMgGtT]?\s*[bB])?\s*$", s)
        if not m:
            return s

        num = m.group(1).replace(',', '.')
        unit = (m.group(2) or '').replace(' ', '')
        unit = unit.upper() if unit else ''

        if unit in ('B', ''):
            unit = 'B' if unit == 'B' else ''
        elif unit in ('KB', 'K B'):
            unit = 'KB'
        elif unit in ('MB', 'M B'):
            unit = 'MB'
        elif unit in ('GB', 'G B'):
            unit = 'GB'

        try:
            val = float(num)
            formatted = f"{val:.2f}"
            return f"{formatted}{unit}"
        except Exception:
            return s

    def _parse_size(size_str: str) -> int:
        """Парсит строку размера и возвращает размер в байтах.
        Примеры: '1.76MB' -> 1843200, '1763KB' -> 1806336, '988KB' -> 1011712, '1000.Kb' -> 1024000
        """
        if not size_str:
            return 0
        
        s = str(size_str).strip()
        m = re.match(r"^\s*([0-9]+(?:[.,][0-9]*)?)\s*([kKmMgGtT]?\s*[bB])?\s*$", s)
        if not m:
            return 0
        
        try:
            num = float(m.group(1).replace(',', '.'))
            unit = (m.group(2) or '').replace(' ', '').upper()
            
            multipliers = {
                'B': 1,
                'KB': 1024,
                'MB': 1024 * 1024,
                'GB': 1024 * 1024 * 1024,
                'TB': 1024 * 1024 * 1024 * 1024
            }
            
            multiplier = multipliers.get(unit, 1)
            return int(num * multiplier)
        except Exception:
            return 0

    try:
        page = int(request.GET.get('page', '1'))
        page_size = int(request.GET.get('page_size', '6'))
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 6
    except ValueError:
        return JsonResponse({"detail": "Некорректные параметры пагинации"}, status=400)

    search = (request.GET.get('search') or '').strip().lower()
    category = (request.GET.get('category') or '').strip()

    try:
        db_path = os.path.join(settings.BASE_DIR, 'books', 'literature.db')
        
        if not os.path.exists(db_path):
            return JsonResponse({"detail": "База данных литературы не найдена"}, status=404)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        where_conditions = []
        params = []

        categories = request.GET.getlist('category')
        if categories and 'all' not in categories:
            # Получаем все категории из базы данных
            cursor.execute("SELECT DISTINCT category FROM literature WHERE category IS NOT NULL AND category != ''")
            all_db_categories = [row[0] for row in cursor.fetchall()]
            
            # Находим категории, которые есть в базе но нет в запросе
            missing_categories = [cat for cat in all_db_categories if cat not in categories]
            
            if missing_categories:
                # Если есть недостающие категории, показываем все записи
                # ИЛИ можно показывать только записи с выбранными категориями + записи с отсутствующими категориями
                placeholders = ','.join(['?' for _ in categories + missing_categories])
                where_conditions.append(f"category IN ({placeholders})")
                params.extend(categories + missing_categories)
            else:
                # Если все категории покрыты, используем стандартный фильтр
                placeholders = ','.join(['?' for _ in categories])
                where_conditions.append(f"category IN ({placeholders})")
                params.extend(categories)

        if search:
            where_conditions.append("(LOWER(title) LIKE ? OR LOWER(authors) LIKE ? OR LOWER(description) LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        order_clause = "ORDER BY title ASC"
        sort_param = request.GET.get('sort', 'default')
        if sort_param != 'default':
            if sort_param == 'title_asc':
                order_clause = "ORDER BY title ASC"
            elif sort_param == 'title_desc':
                order_clause = "ORDER BY title DESC"
            elif sort_param == 'year_desc':
                order_clause = "ORDER BY publishing_date DESC"
            elif sort_param == 'year_asc':
                order_clause = "ORDER BY publishing_date ASC"
            elif sort_param == 'category_asc':
                order_clause = "ORDER BY category ASC"
            elif sort_param == 'category_desc':
                order_clause = "ORDER BY category DESC"
            elif sort_param == 'size_desc':
                order_clause = "ORDER BY title ASC"  # Временная сортировка, будем сортировать в Python
            elif sort_param == 'size_asc':
                order_clause = "ORDER BY title ASC"  # Временная сортировка, будем сортировать в Python

        if sort_param in ['size_desc', 'size_asc']:
            query = f"""
                SELECT rowid, title, faculty, category, authors, publishing_date, 
                       description, image_url, download_size, download_link
                FROM literature 
                {where_clause}
            """
            cursor.execute(query, params)
            all_rows = cursor.fetchall()
            conn.close()
            
            all_items = []
            for row in all_rows:
                (rowid, title, faculty, category, authors, publishing_date, 
                 description, image_url, download_size, download_link) = row
                
                all_items.append({
                    'id': rowid,
                    'title': title or '',
                    'author': authors or '',
                    'description': description or '',
                    'category': category or '',
                    'year': publishing_date or '',
                    'faculty': faculty or '',
                    'downloadUrl': download_link,
                    'downloadSize': _format_size(download_size),
                    'downloadSizeRaw': download_size,
                    'image_url': image_url
                })
            
            reverse = sort_param == 'size_desc'
            all_items.sort(key=lambda x: _parse_size(x.get('downloadSizeRaw', '') or '0'), reverse=reverse)
            
            total = len(all_items)
            start = (page - 1) * page_size
            end = start + page_size
            items = all_items[start:end]
            
        else:
            count_query = f"SELECT COUNT(*) FROM literature {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            limit_clause = f"LIMIT {page_size} OFFSET {offset}"

            query = f"""
                SELECT rowid, title, faculty, category, authors, publishing_date, 
                       description, image_url, download_size, download_link
                FROM literature 
                {where_clause} 
                {order_clause} 
                {limit_clause}
            """
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            items = []
            for row in rows:
                (rowid, title, faculty, category, authors, publishing_date, 
                 description, image_url, download_size, download_link) = row
                
                items.append({
                    'id': rowid,
                    'title': title or '',
                    'author': authors or '',
                    'description': description or '',
                    'category': category or '',
                    'year': publishing_date or '',
                    'faculty': faculty or '',
                    'downloadUrl': download_link,
                    'downloadSize': _format_size(download_size),
                    'image_url': image_url
                })

        return JsonResponse({
            "success": True,
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": items,
        }, status=200, json_dumps_params={'ensure_ascii': False})

    except sqlite3.Error as e:
        return JsonResponse({"detail": "Ошибка базы данных литературы"}, status=500)
    except Exception as e:
        return JsonResponse({"detail": f"Внутренняя ошибка сервера: {str(e)}"}, status=500)


@csrf_exempt
def get_news(request):
    """Возвращает список новостей с пагинацией и фильтрацией.
    
    Параметры GET:
      - page (int) - номер страницы, начиная с 1 (по умолчанию 1)
      - page_size (int) - элементов на страницу (по умолчанию 6)
      - category (str) - фильтр по категории
      - search (str) - поисковая строка
    """
    if request.method != "GET":
        return JsonResponse({"detail": "Метод не разрешён"}, status=405)

    try:
        page = int(request.GET.get('page', '1'))
        page_size = int(request.GET.get('page_size', '6'))
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 6
    except ValueError:
        return JsonResponse({"detail": "Некорректные параметры пагинации"}, status=400)

    search = (request.GET.get('search') or '').strip().lower()
    category = (request.GET.get('category') or '').strip()
    sort_by = (request.GET.get('sort_by') or 'date_desc').strip()

    try:
        db_path = os.path.join(settings.BASE_DIR, 'news', 'times_news.db')
        
        if not os.path.exists(db_path):
            return JsonResponse({"detail": "База данных новостей не найдена"}, status=404)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        where_conditions = []
        params = []

        if category and category != 'all':
            # Фильтруем по полным фразам из тегов
            if category == 'academic':
                where_conditions.append("(tags LIKE ? OR tags LIKE ?)")
                params.extend(['%Преподаватели БНТУ%', '%БНТУ%'])
            elif category == 'achievements':
                where_conditions.append("(tags LIKE ? OR tags LIKE ?)")
                params.extend(['%Спорт%', '%Культура%'])
            elif category == 'education':
                where_conditions.append("(tags LIKE ?)")
                params.append('%Студенты%')
            elif category == 'events':
                where_conditions.append("(tags LIKE ? OR tags LIKE ?)")
                params.extend(['%Мероприятие%', '%Преподаватели БНТУ%'])
            elif category == 'sports':
                where_conditions.append("(tags LIKE ?)")
                params.append('%Спорт%')

        if search:
            where_conditions.append("(LOWER(title) LIKE ? OR LOWER(summary) LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        count_query = f"SELECT COUNT(*) FROM news {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        limit_clause = f"LIMIT {page_size} OFFSET {offset}"

        order_by = "timestamp DESC"  # По умолчанию новые сначала
        if sort_by == 'date_asc':
            order_by = "timestamp ASC"
        elif sort_by == 'title_asc':
            order_by = "title ASC"
        elif sort_by == 'title_desc':
            order_by = "title DESC"

        query = f"""
            SELECT id, title, link, date, summary, tags, image_url, reading_time, timestamp
            FROM news 
            {where_clause} 
            ORDER BY {order_by}
            {limit_clause}
        """
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        items = []
        for row in rows:
            (news_id, title, link, date, summary, tags, image_url, reading_time, timestamp) = row
            
            news_category = 'general'  # категория по умолчанию
            if tags:
                # Определяем категорию на основе того, по какому фильтру пришли
                if category and category != 'all':
                    news_category = category  # Просто присваиваем категорию фильтра
                else:
                    # Только для "all" определяем категорию по тегам
                    tag_words = [word.strip().replace('#', '').lower() for word in tags.split(',')]
                    if 'студенты' in tag_words:
                        news_category = 'education'
                    elif 'мероприятие' in tag_words:
                        news_category = 'events'
                    elif 'спорт' in tag_words:
                        news_category = 'sports'
                    elif 'культура' in tag_words:
                        news_category = 'achievements'
                    elif 'преподаватели бнту' in tag_words or 'бнту' in tag_words:
                        news_category = 'academic'
            
            
            parsed_tags = []
            if tags:
                import re
                tag_list = re.split(r'[,;]\s*', tags.strip())
                parsed_tags = []
                for tag in tag_list:
                    clean_tag = tag.strip()
                    clean_tag = re.sub(r'^#+', '', clean_tag)
                    clean_tag = clean_tag.strip()
                    if clean_tag:
                        parsed_tags.append(clean_tag)
            
            items.append({
                'id': news_id,
                'title': title or '',
                'excerpt': summary or '',
                'content': summary or '',  # Используем summary как контент
                'category': news_category,
                'tags': parsed_tags,  # Добавляем теги
                'author': 'БНТУ',
                'date': date,  # Передаем оригинальную дату
                'timestamp': timestamp,  # Добавляем timestamp для сортировки
                'imageUrl': image_url or '',
                'link': link or '',
                'featured': False,  # Можно определить по тегам если нужно
                'readTime': f"{reading_time or 5} мин"
            })

        return JsonResponse({
            "success": True,
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": items,
        }, status=200, json_dumps_params={'ensure_ascii': False})

    except sqlite3.Error as e:
        return JsonResponse({"detail": "Ошибка базы данных новостей"}, status=500)
    except Exception as e:
        return JsonResponse({"detail": f"Внутренняя ошибка сервера: {str(e)}"}, status=500)
