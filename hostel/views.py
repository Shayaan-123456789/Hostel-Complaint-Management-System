"""JSON APIs for STUDENT, WARDEN, STAFF using the final Oracle schema."""
import mimetypes
from pathlib import Path

from django.contrib.auth.hashers import check_password, make_password
from django.http import FileResponse

from . import database as db
from .common import (endpoint, response, payload, required, optional,
                     integer, email_address, password_strength, choice, paging)
from .media import delete_photo, private_photo_path, save_photo
from .security import ApiError, verify_login

PRIORITIES = {'LOW', 'MEDIUM', 'HIGH', 'URGENT'}
STATUSES = {'OPEN', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'}
ROOM_TYPES = {'SINGLE', 'DOUBLE', 'TRIPLE', 'DORMITORY'}


def _check_found(row):
    if not row:
        raise ApiError('Record not found.', 404)
    return row


def _can_read(conn, actor, complaint_id):
    """Do not reveal the existence of complaints the caller cannot access."""
    if actor['role'] == 'WARDEN':
        return True
    if actor['role'] == 'STUDENT':
        accessible = db.value(conn, 'SELECT 1 FROM complaint WHERE complaint_id = ? AND student_id = ?',
                              [complaint_id, actor['id']])
    else:
        accessible = db.value(conn, '''SELECT 1 FROM complaint_assignment
                   WHERE complaint_id = ? AND staff_id = ? AND ROWNUM = 1''',
                              [complaint_id, actor['id']])
    if not accessible:
        raise ApiError('Complaint not found.', 404)
    return True


def _active_assignee(conn, staff_id, complaint_id):
    return bool(db.value(conn, '''SELECT 1 FROM complaint_assignment
       WHERE complaint_id = ? AND staff_id = ? AND completed_date IS NULL AND ROWNUM = 1''',
       [complaint_id, staff_id]))


def _record_upload(request, uploaded):
    saved = save_photo(uploaded)
    if saved:
        request._hostel_saved_paths.append(saved)
    return saved


@endpoint(public=True)
def health(request, conn, actor):
    db.value(conn, 'SELECT 1 FROM dual')
    return response({'status': 'ok', 'oracle': 'connected'})


@endpoint(methods=('POST',), public=True, write=True)
def register_student(request, conn, actor):
    data = payload(request)
    email = email_address(required(data, 'email', 120))
    password = password_strength(data.get('password'))
    student_id = db.call_with_id(conn, 'sp_register_student', [
        required(data, 'name', 100), email, make_password(password),
        optional(data, 'phone', 15), integer(data, 'room_id', high=999999),
    ])
    return response({'message': 'Student account created. Please sign in.', 'student_id': student_id}, 201)


@endpoint(methods=('POST',), public=True)
def login(request, conn, actor):
    data = payload(request)
    role = required(data, 'role', 16).upper()
    if role == 'ADMIN':
        role = 'WARDEN'
    identity = required(data, 'username' if role == 'WARDEN' else 'email', 120)
    password = data.get('password')
    if not isinstance(password, str) or not password or len(password) > 128:
        raise ApiError('Password is required.')
    return response(verify_login(conn, role, identity, password))


@endpoint()
def me(request, conn, actor):
    return response({'user': actor})


@endpoint(methods=('POST',), roles=('STUDENT', 'STAFF'), write=True)
def change_password(request, conn, actor):
    data = payload(request)
    current = data.get('current_password')
    if not isinstance(current, str) or not current or len(current) > 128:
        raise ApiError('Current password is required.')
    new = password_strength(data.get('new_password'))
    if current == new:
        raise ApiError('The new password must be different.')
    table, pk = ('student', 'student_id') if actor['role'] == 'STUDENT' else ('staff', 'staff_id')
    row = _check_found(db.one(conn, f'SELECT password FROM {table} WHERE {pk} = ?', [actor['id']]))
    if not check_password(current, row['password']):
        raise ApiError('Current password is incorrect.', 403)
    db.run(conn, f'UPDATE {table} SET password = ? WHERE {pk} = ?', [make_password(new), actor['id']])
    return response({'message': 'Password updated. Sign in again; previous tokens are now invalid.'})


@endpoint(public=True)
def rooms(request, conn, actor):
    return response({'rooms': db.all_rows(conn, '''
       SELECT r.room_id, r.room_number, r.block, r.capacity, r.room_type,
              COUNT(s.student_id) AS occupied,
              r.capacity - COUNT(s.student_id) AS available
         FROM room r LEFT JOIN student s ON s.room_id = r.room_id AND s.status = 'ACTIVE'
        GROUP BY r.room_id, r.room_number, r.block, r.capacity, r.room_type
        ORDER BY r.block, r.room_number''')})


@endpoint(public=True)
def categories(request, conn, actor):
    return response({'categories': db.all_rows(conn,
        'SELECT category_id, category_name, description FROM category ORDER BY category_name')})


@endpoint(methods=('POST',), roles=('WARDEN',), write=True)
def create_room(request, conn, actor):
    data = payload(request)
    room_type = choice(data, 'room_type', ROOM_TYPES)
    db.run(conn, 'INSERT INTO room (room_number, block, capacity, room_type) VALUES (?, ?, ?, ?)', [
        required(data, 'room_number', 10), required(data, 'block', 10),
        integer(data, 'capacity', 1, 99), room_type,
    ])
    return response({'room_id': int(db.value(conn, 'SELECT seq_room.CURRVAL FROM dual'))}, 201)


@endpoint(methods=('POST',), roles=('WARDEN',), write=True)
def create_category(request, conn, actor):
    data = payload(request)
    db.run(conn, 'INSERT INTO category (category_name, description) VALUES (?, ?)', [
        required(data, 'category_name', 50), optional(data, 'description', 200),
    ])
    return response({'category_id': int(db.value(conn, 'SELECT seq_category.CURRVAL FROM dual'))}, 201)


@endpoint(methods=('GET', 'POST'), write=True)
def complaints(request, conn, actor):
    if request.method == 'GET':
        filters = []
        params = []
        if actor['role'] == 'STUDENT':
            filters.append('v.student_id = ?')
            params.append(actor['id'])
        elif actor['role'] == 'STAFF':
            # A member of staff can still see a previously completed assignment.
            filters.append('EXISTS (SELECT 1 FROM complaint_assignment a WHERE a.complaint_id = v.complaint_id AND a.staff_id = ?)')
            params.append(actor['id'])
        for query_key, column in [
            ('status', 'v.status'), ('priority', 'v.priority'),
            ('category', 'v.category_name'), ('block', 'v.block'),
        ]:
            value = request.GET.get(query_key)
            if value:
                if query_key in ('status', 'priority'):
                    value = value.upper()
                    if value not in (STATUSES if query_key == 'status' else PRIORITIES):
                        raise ApiError(f'Invalid {query_key} filter.')
                filters.append(f'{column} = ?')
                params.append(value)
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        limit, offset = paging(request)
        count = db.value(conn, 'SELECT COUNT(*) FROM v_complaint_details v' + where, params)
        rows = db.page(conn, '''SELECT v.* FROM v_complaint_details v''' + where + '''
            ORDER BY CASE v.priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3 ELSE 4 END, v.created_date DESC, v.complaint_id DESC''',
            params, limit, offset)
        return response({'total': int(count), 'limit': limit, 'offset': offset, 'complaints': rows})

    # POST: Student owns the complaint; use the SQL stored procedure for atomic photo+complaint.
    if actor['role'] != 'STUDENT':
        raise ApiError('Only students can submit complaints.', 403)
    data = payload(request)
    photo = _record_upload(request, request.FILES.get('photo'))
    complaint_id = db.call_with_id(conn, 'sp_submit_complaint', [
        actor['id'], integer(data, 'category_id', high=9999),
        required(data, 'title', 150), required(data, 'description', 2000),
        choice(data, 'priority', PRIORITIES, 'MEDIUM'), photo,
    ])
    return response({'message': 'Complaint submitted.', 'complaint_id': complaint_id}, 201)


@endpoint()
def complaint_summary(request, conn, actor):
    """Accurate role-scoped counts without fetching every complaint."""
    where, params = '', []
    if actor['role'] == 'STUDENT':
        where = 'WHERE c.student_id = ?'
        params = [actor['id']]
    elif actor['role'] == 'STAFF':
        where = '''WHERE EXISTS (SELECT 1 FROM complaint_assignment a
                          WHERE a.complaint_id = c.complaint_id AND a.staff_id = ?)'''
        params = [actor['id']]
    totals = db.one(conn, f'''SELECT COUNT(*) AS total,
        SUM(CASE WHEN c.status = 'OPEN' THEN 1 ELSE 0 END) AS open_count,
        SUM(CASE WHEN c.status = 'ASSIGNED' THEN 1 ELSE 0 END) AS assigned_count,
        SUM(CASE WHEN c.status = 'IN_PROGRESS' THEN 1 ELSE 0 END) AS in_progress_count,
        SUM(CASE WHEN c.status = 'RESOLVED' THEN 1 ELSE 0 END) AS resolved_count,
        SUM(CASE WHEN c.status = 'CLOSED' THEN 1 ELSE 0 END) AS closed_count
        FROM complaint c {where}''', params)
    return response({'summary': totals})


@endpoint()
def complaint_detail(request, conn, actor, complaint_id):
    _can_read(conn, actor, complaint_id)
    detail = _check_found(db.one(conn,
        'SELECT * FROM v_complaint_details WHERE complaint_id = ?', [complaint_id]))
    detail['photos'] = db.all_rows(conn, '''SELECT photo_id, uploaded_date FROM complaint_photo
                 WHERE complaint_id = ? ORDER BY uploaded_date''', [complaint_id])
    detail['history'] = db.all_rows(conn, '''SELECT status_id, old_status, new_status, changed_by, change_date
           FROM complaint_status WHERE complaint_id = ? ORDER BY status_id''', [complaint_id])
    detail['feedback'] = db.one(conn, '''SELECT rating, comments, feedback_date FROM complaint_feedback
                     WHERE complaint_id = ?''', [complaint_id])
    detail['assignments'] = db.all_rows(conn, '''SELECT a.assignment_id, a.staff_id, st.name AS staff_name,
           a.assigned_date, a.completed_date FROM complaint_assignment a JOIN staff st ON st.staff_id = a.staff_id
           WHERE a.complaint_id = ? ORDER BY a.assigned_date''', [complaint_id])
    return response({'complaint': detail})


@endpoint(methods=('POST',), roles=('STUDENT',), write=True)
def add_photo(request, conn, actor, complaint_id):
    # Lock the complaint while validating state, preventing a close/resolve race.
    row = db.one(conn, 'SELECT student_id, status FROM complaint WHERE complaint_id = ? FOR UPDATE', [complaint_id])
    if not row or row['student_id'] != actor['id']:
        raise ApiError('Complaint not found.', 404)
    if row['status'] in ('RESOLVED', 'CLOSED'):
        raise ApiError('Cannot add photos after resolution.')
    upload = request.FILES.get('photo')
    if upload is None:
        raise ApiError('A photo upload is required.')
    saved = _record_upload(request, upload)
    db.call(conn, 'sp_add_photo', [complaint_id, saved])
    return response({'message': 'Photo added.'}, 201)


@endpoint()
def download_photo(request, conn, actor, complaint_id, photo_id):
    _can_read(conn, actor, complaint_id)
    row = db.one(conn,
        'SELECT photo_path FROM complaint_photo WHERE complaint_id = ? AND photo_id = ?',
        [complaint_id, photo_id])
    _check_found(row)
    path = private_photo_path(row['photo_path'])
    result = FileResponse(path.open('rb'), content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
    result['Cache-Control'] = 'private, no-store'
    result['Content-Disposition'] = f'inline; filename="{path.name}"'
    return result


@endpoint(methods=('POST',), roles=('WARDEN',), write=True)
def assign(request, conn, actor, complaint_id):
    data = payload(request)
    staff_id = integer(data, 'staff_id', high=999999)
    # Do not rely solely on the browser's department filter. Verify that the
    # selected staff member is active and matches this complaint's category.
    # This is an application workflow rule; the nine-table schema is unchanged.
    eligibility = db.one(conn, '''SELECT c.category_name AS complaint_category,
                                s.department AS staff_department, s.status AS staff_status
                           FROM complaint co
                           JOIN category c ON c.category_id = co.category_id
                           CROSS JOIN staff s
                          WHERE co.complaint_id = ? AND s.staff_id = ?''',
                         [complaint_id, staff_id])
    if not eligibility:
        raise ApiError('Complaint or maintenance staff member not found.', 404)
    if str(eligibility['staff_status']).strip().upper() != 'ACTIVE':
        raise ApiError('Only active maintenance staff can receive complaints.')
    if str(eligibility['complaint_category']).strip().casefold() != str(eligibility['staff_department']).strip().casefold():
        raise ApiError('The selected technician must belong to the complaint category department.')
    db.call(conn, 'sp_assign_complaint', [
        complaint_id, staff_id, f'WARDEN:{actor["id"]}',
    ])
    return response({'message': 'Complaint assigned; status changed to ASSIGNED.'})


@endpoint(methods=('POST',), roles=('WARDEN', 'STAFF'), write=True)
def update_status(request, conn, actor, complaint_id):
    data = payload(request)
    new_status = choice(data, 'status', {'IN_PROGRESS', 'RESOLVED', 'CLOSED'})
    if actor['role'] == 'STAFF':
        if new_status == 'CLOSED':
            raise ApiError('Only a warden can close a complaint.', 403)
        if not _active_assignee(conn, actor['id'], complaint_id):
            raise ApiError('The complaint is not assigned to you.', 403)
    remark = optional(data, 'resolution_remark', 1000)
    if new_status == 'RESOLVED' and not remark:
        raise ApiError('resolution_remark is required when resolving a complaint.')
    db.call(conn, 'sp_update_status', [
        complaint_id, new_status, remark, f'{actor["role"]}:{actor["id"]}',
    ])
    return response({'message': f'Complaint status changed to {new_status}.'})


@endpoint(methods=('POST',), roles=('STUDENT',), write=True)
def feedback(request, conn, actor, complaint_id):
    data = payload(request)
    db.call(conn, 'sp_submit_feedback', [
        complaint_id, actor['id'], integer(data, 'rating', 1, 5),
        optional(data, 'comments', 1000),
    ])
    return response({'message': 'Feedback submitted.'}, 201)


@endpoint(roles=('WARDEN',))
def dashboard(request, conn, actor):
    by_category = db.all_rows(conn, 'SELECT category_name, status, complaint_count FROM v_dashboard_summary ORDER BY category_name, status')
    totals = db.all_rows(conn, '''SELECT status, COUNT(*) AS total FROM complaint GROUP BY status ORDER BY status''')
    counts = db.one(conn, '''SELECT COUNT(*) AS total_complaints,
           COUNT(CASE WHEN status IN ('OPEN','ASSIGNED','IN_PROGRESS') THEN 1 END) AS pending,
           COUNT(CASE WHEN status IN ('RESOLVED','CLOSED') THEN 1 END) AS resolved
           FROM complaint''')
    ratings = db.all_rows(conn, '''SELECT cat.category_name, COUNT(f.feedback_id) AS feedback_count,
           ROUND(AVG(f.rating), 2) AS average_rating
           FROM category cat LEFT JOIN complaint c ON c.category_id = cat.category_id
           LEFT JOIN complaint_feedback f ON f.complaint_id = c.complaint_id
           GROUP BY cat.category_name ORDER BY cat.category_name''')
    return response({'totals': counts, 'by_status': totals, 'by_category_status': by_category, 'ratings': ratings})


@endpoint(roles=('WARDEN',))
def staff_collection(request, conn, actor):
    if request.method == 'GET':
        staff = db.all_rows(conn, '''SELECT st.staff_id, st.name, st.email, st.department, st.phone, st.status,
             COUNT(a.assignment_id) AS active_assignments FROM staff st
             LEFT JOIN complaint_assignment a ON a.staff_id = st.staff_id AND a.completed_date IS NULL
             GROUP BY st.staff_id, st.name, st.email, st.department, st.phone, st.status
             ORDER BY st.name''')
        return response({'staff': staff})


def _staff_department(conn, value):
    """Validate technician departments against the live CATEGORY table.

    A dropdown is a UI convenience, not an API authorization boundary.
    Normalize to the stored category spelling, so assignments always match.
    """
    department = required({'department': value}, 'department', 50)
    record = db.one(conn, '''SELECT category_name FROM category
       WHERE UPPER(TRIM(category_name)) = UPPER(TRIM(?))
         AND ROWNUM = 1''', [department])
    if not record:
        raise ApiError('Department must match an existing complaint category.')
    return record['category_name']


@endpoint(methods=('POST',), roles=('WARDEN',), write=True)
def create_staff(request, conn, actor):
    data = payload(request)
    email = email_address(required(data, 'email', 120))
    password = password_strength(data.get('password'))
    db.run(conn, '''INSERT INTO staff (name, email, password, department, phone)
       VALUES (?, ?, ?, ?, ?)''', [
       required(data, 'name', 100), email, make_password(password),
       _staff_department(conn, data.get('department')), optional(data, 'phone', 15),
    ])
    return response({'staff_id': int(db.value(conn, 'SELECT seq_staff.CURRVAL FROM dual'))}, 201)


@endpoint(methods=('PATCH',), roles=('WARDEN',), write=True)
def staff_member(request, conn, actor, staff_id):
    data = payload(request)
    _check_found(db.one(conn, 'SELECT staff_id FROM staff WHERE staff_id = ? FOR UPDATE', [staff_id]))
    allowed = {
        'name': lambda x: required({'name': x}, 'name', 100),
        'department': lambda x: _staff_department(conn, x),
        'phone': lambda x: optional({'phone': x}, 'phone', 15),
        'status': lambda x: choice({'status': x}, 'status', {'ACTIVE', 'INACTIVE'}),
    }
    if not data or set(data) - set(allowed):
        raise ApiError('Only name, department, phone and status may be updated.')
    if isinstance(data.get('status'), str) and data['status'].strip().upper() == 'INACTIVE':
        pending = db.value(conn, '''SELECT COUNT(*) FROM complaint_assignment
                         WHERE staff_id = ? AND completed_date IS NULL''', [staff_id])
        if pending:
            raise ApiError('Cannot deactivate staff with unfinished assignments.')
    fields = []
    params = []
    for key, validation in allowed.items():
        if key in data:
            fields.append(f'{key} = ?')
            params.append(validation(data[key]))
    db.run(conn, 'UPDATE staff SET ' + ', '.join(fields) + ' WHERE staff_id = ?', [*params, staff_id])
    return response({'message': 'Staff member updated.'})


@endpoint(methods=('POST',), roles=('WARDEN',), write=True)
def reset_staff_password(request, conn, actor, staff_id):
    data = payload(request)
    new = password_strength(data.get('new_password'))
    _check_found(db.one(conn, 'SELECT staff_id FROM staff WHERE staff_id = ? FOR UPDATE', [staff_id]))
    db.run(conn, 'UPDATE staff SET password = ? WHERE staff_id = ?', [make_password(new), staff_id])
    return response({'message': 'Staff password reset; existing tokens are now invalid.'})


@endpoint(roles=('WARDEN',))
def students(request, conn, actor):
    limit, offset = paging(request)
    rows = db.page(conn, '''SELECT s.student_id, s.name, s.email, s.phone, s.status,
          s.room_id, r.block, r.room_number FROM student s
          JOIN room r ON r.room_id = s.room_id ORDER BY s.student_id DESC''', [], limit, offset)
    total = db.value(conn, 'SELECT COUNT(*) FROM student')
    return response({'students': rows, 'total': int(total), 'limit': limit, 'offset': offset})


@endpoint(methods=('POST',), roles=('WARDEN',), write=True)
def escalate(request, conn, actor):
    data = payload(request)
    days = integer(data, 'days', 0, 365) if 'days' in data else 3
    db.call(conn, 'sp_escalate_overdue', [days])
    return response({'message': 'Eligible overdue complaints escalated by one priority level.', 'days': days})


@endpoint(roles=('WARDEN', 'STAFF'))
def workload(request, conn, actor):
    clause, args = ('WHERE st.staff_id = ?', [actor['id']]) if actor['role'] == 'STAFF' else ('', [])
    result = db.all_rows(conn, f'''SELECT st.staff_id, st.name, st.department,
       COUNT(a.assignment_id) AS pending_work
       FROM staff st LEFT JOIN complaint_assignment a ON a.staff_id = st.staff_id
       AND a.completed_date IS NULL
       AND EXISTS (SELECT 1 FROM complaint c WHERE c.complaint_id = a.complaint_id
                   AND c.status IN ('ASSIGNED','IN_PROGRESS'))
       {clause} GROUP BY st.staff_id, st.name, st.department ORDER BY pending_work DESC, st.name''', args)
    return response({'workload': result})
