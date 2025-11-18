from flask import Flask, render_template, request, redirect, url_for, flash, session
import config
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import os

app = Flask(__name__)
app.secret_key = "qwertyuiop"

# ---------- MySQL config ----------
app.config['MYSQL_HOST'] = config.MYSQL_HOST
app.config['MYSQL_USER'] = config.MYSQL_USER
# Use environment variable if available (recommended for PythonAnywhere)
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', config.MYSQL_PASSWORD)
app.config['MYSQL_DB'] = config.MYSQL_DB
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# ---------- Index / Tasks ----------
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        flash("Please log in to continue.", 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Add task
    if request.method == 'POST':
        task = request.form.get('task', '').strip()
        dueDate = request.form.get('dueDate', '').strip()
        if not task or not dueDate:
            flash('Task and due date are required!', 'error')
            return redirect(url_for('index'))

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "INSERT INTO tasks (task, dueDate, userId) VALUES (%s,%s,%s)",
                (task, dueDate, user_id)
            )
            mysql.connection.commit()
            flash('Task added successfully!', 'success')
        except Exception as e:
            mysql.connection.rollback()
            flash('Error adding task!', 'error')
            app.logger.exception("Task insert error")
        finally:
            cur.close()
        return redirect(url_for('index'))

    # Fetch tasks
    now = date.today()
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            "SELECT id, task, dateCreated, dueDate, isCompleted FROM tasks WHERE userId=%s ORDER BY id ASC",
            (user_id,)
        )
        tasks = cur.fetchall()
        for t in tasks:
            if isinstance(t['dueDate'], datetime):
                t['dueDate'] = t['dueDate'].date()
            if isinstance(t['dateCreated'], datetime):
                t['dateCreated'] = t['dateCreated'].date()
            t['isCompleted'] = bool(t['isCompleted'])
    except Exception as e:
        app.logger.exception("Error fetching tasks")
        tasks = []
    finally:
        cur.close()

    return render_template("index.html", tasks=tasks, now=now)


# ---------- Complete / Undo ----------
@app.route('/complete/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT isCompleted FROM tasks WHERE id=%s AND userId=%s", (task_id, session['user_id']))
        task = cur.fetchone()
        if task:
            new_status = 0 if task['isCompleted'] else 1
            cur.execute("UPDATE tasks SET isCompleted=%s WHERE id=%s AND userId=%s",
                        (new_status, task_id, session['user_id']))
            mysql.connection.commit()
            flash('Task status updated!', 'success')
        else:
            flash('Task not found!', 'error')
    except Exception as e:
        mysql.connection.rollback()
        flash('Error updating task!', 'error')
        app.logger.exception("Error toggling task completion")
    finally:
        cur.close()
    return redirect(url_for('index'))


# ---------- Delete Task ----------
@app.route('/delete/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM tasks WHERE id=%s AND userId=%s", (task_id, session['user_id']))
        mysql.connection.commit()
        flash('Task deleted!', 'success')
    except:
        mysql.connection.rollback()
        flash('Error deleting task!', 'error')
    finally:
        cur.close()
    return redirect(url_for('index'))


# ---------- Update Task ----------
@app.route('/update/<int:task_id>', methods=['GET', 'POST'])
def update_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    if request.method == 'POST':
        task = request.form.get('task', '').strip()
        dueDate = request.form.get('dueDate', '').strip()
        try:
            cur.execute(
                "UPDATE tasks SET task=%s, dueDate=%s WHERE id=%s AND userId=%s",
                (task, dueDate, task_id, session['user_id'])
            )
            mysql.connection.commit()
            flash('Task updated!', 'success')
            return redirect(url_for('index'))
        except:
            mysql.connection.rollback()
            flash('Error updating task!', 'error')
        finally:
            cur.close()
    else:
        cur.execute("SELECT task, dueDate FROM tasks WHERE id=%s AND userId=%s", (task_id, session['user_id']))
        t = cur.fetchone()
        cur.close()
        if not t:
            flash('Task not found', 'error')
            return redirect(url_for('index'))
        return render_template('update_task.html', task=t, task_id=task_id)


# ---------- Register ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        if not username or not email or not password or not password2:
            flash('Please fill out all fields!', 'error')
            return render_template("register.html")

        if password != password2:
            flash('Passwords do not match!', 'error')
            return render_template("register.html")

        if len(password) < 7:
            flash('Password must be at least 7 characters!', 'error')
            return render_template("register.html")

        hashed_pass = generate_password_hash(password)
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id FROM users WHERE email=%s OR username=%s", (email, username))
            existing = cur.fetchone()
            if existing:
                flash('Email or username already exists', 'error')
                return render_template("register.html")

            cur.execute("INSERT INTO users (username, email, password) VALUES (%s,%s,%s)",
                        (username, email, hashed_pass))
            mysql.connection.commit()
            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))
        except:
            mysql.connection.rollback()
            flash('Error creating account!', 'error')
        finally:
            cur.close()
    return render_template("register.html")


# ---------- Login ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Provide both email and password', 'error')
            return render_template("signin.html")

        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT id, username, password FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
        finally:
            cur.close()

        if not user:
            flash('Invalid credentials', 'error')
            return render_template("signin.html")

        if check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')

    return render_template("signin.html")


# ---------- Logout ----------
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out!', 'success')
    return redirect(url_for('login'))


# ---------- Main ----------
if __name__ == '__main__':
    app.run(debug=True)
