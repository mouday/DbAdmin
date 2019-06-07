# -*- coding: utf-8 -*-

# @Date    : 2019-06-06
# @Author  : Peng Shiyu

import datetime

import pickledb
from flask import (
    Flask,
    render_template,
    request,
    url_for,
    redirect,
    flash,
    session
)

from sqlalchemy import create_engine, text
from tinydb import Query, TinyDB

import os

# 全局基础路径配置
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")

# 全局用户表
user_db = TinyDB(os.path.join(data_dir, "user.json"))
username_config = user_db.table("username")

# 全局访问历史
history_db = TinyDB(os.path.join(data_dir, "history.json"))
history_config = history_db.table("history")

# 全局登录会话表
login_db = pickledb.load(os.path.join(data_dir, "login.db"), True)
query = Query()

# 最近访问
recently_visited = "最近访问"

app = Flask(__name__)

app.secret_key = "KDL88t0LCcJgvgTVpU+ASU4RrO0rP/hwcSil1NBnVfc="


def get_table(username, table):
    """
    获取用户表
    """
    tiny_db = TinyDB(os.path.join(data_dir, "_{}.json".format(username)))
    return tiny_db.table(table)


#########################################
# 权限验证 + 访问历史记录
#########################################
@app.before_request
def login_check():
    username = session.get("username")

    # 放行路径
    exclude_paths = [
        "/static",
        "/login"
    ]
    for exclude_path in exclude_paths:
        if request.path.startswith(exclude_path):
            return None

    # 登录验证
    if not login_db.get(username):
        flash("未登录，请登录", "warning")
        return redirect(url_for("login"))


@app.before_request
def request_history():
    username = session.get("username")
    history_config.insert(
        {
            "username": username,
            "path": request.path,
            "create_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )


#########################################
# 登录验证
#########################################
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        result = username_config.search(
            (query.username == username) &
            (query.password == password)
        )

        if result:
            login_db.set(username, password)
            session["username"] = username
            return redirect(url_for("index"))
        else:
            flash("账号或密码错误", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    username = session.get("username")
    login_db.rem(username)
    return redirect(url_for("login"))


@app.route("/")
def index():
    database_config = get_table(session.get("username"), "database")

    items = database_config.all()
    items.insert(
        0,
        {
            "database_name": recently_visited
        }
    )
    return render_template("index.html", items=items)


#########################################
# 数据库配置
#########################################
@app.route("/database")
def database():
    database_config = get_table(session.get("username"), "database")

    keys = ["database_name", "database_url"]

    items = database_config.all()

    paths = [{
        "name": "数据库配置",
        "url": url_for("database")
    }]
    return render_template("database.html", keys=keys, items=items, paths=paths)


@app.route("/addDatabase", methods=["POST"])
def add_database():
    database_name = request.form.get("database_name")
    database_url = request.form.get("database_url")

    database_config = get_table(session.get("username"), "database")

    database_config.insert(
        {
            "database_name": database_name,
            "database_url": database_url,
        }
    )
    return redirect(url_for("database"))


@app.route("/deleteDatabase")
def delete_database():
    database_name = request.args.get("database_name")

    database_config = get_table(session.get("username"), "database")

    database_config.remove(query.database_name == database_name)
    return redirect(url_for("database"))


#########################################
# 表列表和表数据
#########################################
@app.route("/table")
def table():
    database_name = request.args.get("database_name")

    # 配置要显示的字段
    keys = ["Name", "Comment", "Create_time"]

    database_config = get_table(session.get("username"), "database")
    table_config = get_table(session.get("username"), "table")

    if database_name == recently_visited:
        items = table_config.all()
    elif database_name == "history":
        return redirect(url_for("table_detail", database_name="history"))

    else:
        database = database_config.search(query.database_name == database_name)[0]
        sql = "show table status"
        engine = create_engine(database["database_url"])
        con = engine.connect()
        cursor = con.execute(sql)
        items = []

        for row in cursor:
            item = {}
            for key in keys:
                item[key] = getattr(row, key)
            item["database_name"] = database_name
            items.append(item)

        con.close()

    paths = [{
        "name": database_name,
        "url": url_for("table", database_name=database_name)
    }]

    return render_template("table-list.html", keys=keys, items=items, paths=paths)


@app.route("/table-detail")
def table_detail():
    database_name = request.args.get("database_name")
    table = request.args.get("table")
    page = request.args.get("page", "1")

    # 分页
    page = int(page)
    offset = 20

    previous_page = page - 1
    next_page = page + 1

    if page > 1:
        page -= 1
    else:
        page = 0

    # 兼容历史记录表
    if database_name == "history":
        items = history_config.all()[page * offset: (page + 1) * offset]
        keys = ["username", "path", "create_time"]

    else:
        database_config = get_table(session.get("username"), "database")

        database = database_config.search(query.database_name == database_name)[0]
        engine = create_engine(database["database_url"])
        sql = "select * from {table} limit :limit, :offset".format(table=table)

        con = engine.connect()
        cursor = con.execute(text(sql), {"offset": offset, "limit": page * offset})
        con.close()
        items = cursor
        keys = cursor.keys()

    paths = [
        {
            "name": database_name,
            "url": url_for("table", database_name=database_name)
        },
        {
            "name": table,
            "url": url_for("table_detail", database_name=database_name, table=table)
        },
        {
            "name": page + 1,
            "url": url_for("table_detail", database_name=database_name, table=table, page=page + 1)
        }
    ]

    # 更新最近访问的数据表
    table_config = get_table(session.get("username"), "table")
    table_config.remove(
        query.database_name == database_name
        and query.Name == table
    )

    tables = table_config.all()[0:49]
    tables.insert(
        0,
        {
            "Name": table,
            "Comment": database_name,
            "Create_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )
    table_config.purge()
    table_config.insert_multiple(tables)

    # 配置要返回的参数
    dct = {
        "database_name": database_name,
        "table": table,
        "keys": keys,
        "items": items,
        "paths": paths,
        "next_page": next_page,
        "previous_page": previous_page
    }

    return render_template("table-detail.html", **dct)


#########################################
# 用户管理
#########################################
@app.route("/admin")
def admin():
    items = username_config.all()

    keys = ["username", "password"]
    paths = [
        {
            "name": "admin",
            "url": url_for("admin")
        }
    ]

    return render_template("admin.html", keys=keys, items=items, paths=paths)


@app.route("/addUser", methods=["POST"])
def add_user():
    username = request.form.get("username")
    password = request.form.get("password")

    username_config.insert(
        {
            "username": username,
            "password": password
        }
    )
    flash("添加用户成功", "success")
    return redirect(url_for("admin"))


@app.route("/deleteUser")
def delete_user():
    username = request.args.get("username")

    username_config.remove(query.username == username)

    flash("删除用户成功", "warning")
    return redirect(url_for("admin"))


if __name__ == '__main__':
    app.run(debug=True)
