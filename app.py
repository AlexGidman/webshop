from flask import Flask, send_from_directory, render_template, request, redirect, url_for, g, flash
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileRequired
from wtforms import StringField, TextAreaField, SubmitField, SelectField, DecimalField, FileField
from wtforms.validators import InputRequired, DataRequired, Length
from werkzeug.utils import secure_filename
# import pdb
import sqlite3
import os
import datetime
from secrets import token_hex

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev"
app.config["ALLOWED_IMAGE_EXTENSIONS"] = ["jpeg", "jpg", "png"]
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["IMAGE_UPLOADS"] = os.path.join(basedir, "uploads")

class ItemForm(FlaskForm):
    title = StringField("Title", validators=[InputRequired("Input is required!"), DataRequired("Data is required!"),
                                             Length(min=5, max=20, message="Input must be between 5 & 20 characters!")])
    price = DecimalField("Price")
    description = TextAreaField("Description",
                                validators=[InputRequired("Input is required!"), DataRequired("Data is required!"),
                                            Length(min=5, max=40, message="Input must be between 5 & 40 characters!")])
    image       = FileField("Image", validators=[FileRequired(), FileAllowed(app.config["ALLOWED_IMAGE_EXTENSIONS"], "Images only!")])

class NewItemForm(ItemForm):
    category    = SelectField("Category", coerce=int)
    subcategory = SelectField("Subcategory", coerce=int)
    submit      = SubmitField("Submit")

class EditItemForm(ItemForm):
    submit      = SubmitField("Update item")

class DeleteItemForm(FlaskForm):
    submit      = SubmitField("Delete item")

class FilterForm(FlaskForm):
    title       = StringField("Title", validators=[Length(max=20)])
    price       = SelectField("Price", coerce=int, choices=[(0, "---"), (1, "Max to Min"), (2, "Min to Max")])
    category    = SelectField("Category", coerce=int)
    subcategory = SelectField("Subcategory", coerce=int)
    submit      = SubmitField("Filter")


# UPDATE ITEM
@app.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):
    conn = get_db()
    c = conn.cursor()
    item_from_db = c.execute("SELECT * FROM items WHERE id =?", (item_id,))
    row = c.fetchone()
    try:
        item = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "price": row[3],
            "image": row[4]
        }
    except:
        item = {}

    if item:
        form = EditItemForm()
        if form.validate_on_submit():
            c.execute("""UPDATE items SET title = ?, description = ?, price = ? WHERE id = ? """,
                      (form.title.data, form.description.data, float(form.price.data), item_id))
            conn.commit()

            flash("Item {} has been successfully updated".format(form.title.data), "success")
            return redirect(url_for("item", item_id=item_id))
        # pre-populates the edit form with values taken from database
        form.title.data = item["title"]
        form.description.data = item["description"]
        form.price.data = item["price"]

        if form.errors:
            flash("{}".format(form.errors), "danger")
        return render_template("edit_item.html",
                               item=item,
                               form=form)

    return redirect(url_for('home'))

# DELETE ITEM
@app.route("/item/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    row = c.fetchone()
    try:
        item = {
            "id": row[0],
            "title": row[1]
        }
    except:
        item = {}

    if item:
        c.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        flash("Item {} successfully deleted".format(item['title']),)
    else:
        flash("This item does not exist.", "danger")

    return redirect(url_for('home'))


# READ ITEM
@app.route("/item/<int:item_id>")
def item(item_id):
    c = get_db().cursor()
    c.execute("""SELECT
                i.id, i.title, i.description, i.price, i.image, c.name, s.name
                FROM
                items AS i
                INNER JOIN categories AS c ON i.category_id = c.id
                INNER JOIN subcategories AS s ON i.subcategory_id = s.id
                WHERE i.id = ?""",
                (item_id,)
    )
    row = c.fetchone()

    try:
        item = {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "price": row[3],
                "image": row[4],
                "category": row[5],
                "subcategory": row[6]
        }
    except:
        item = {}

    if item:
        deleteItemForm = DeleteItemForm()

        return render_template("item.html",
                               item=item,
                               deleteItemForm=deleteItemForm)
    return redirect(url_for("home"))


# HOME
@app.route("/")
def home():
    conn = get_db()
    c = conn.cursor()

    form = FilterForm(request.args, meta={"csrf": False})

    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    categories.insert(0, (0, "---"))
    form.category.choices = categories

    c.execute("SELECT id, name FROM subcategories WHERE category_id = ?", (1,))
    subcategories = c.fetchall()
    subcategories.insert(0, (0, "---"))
    form.subcategory.choices = subcategories

    query = """SELECT i.id, i.title, i.description, i.price, i.image, c.name, s.name 
            FROM items AS i 
            INNER JOIN categories AS c ON i.category_id = c.id 
            INNER JOIN subcategories AS s ON i.subcategory_id = s.id"""

    if form.validate():
        filter_queries = []
        parameters = []

        if form.title.data.strip():
            filter_queries.append("i.title LIKE ?")
            parameters.append("%" + form.title.data + "%")

        if form.category.data:
            filter_queries.append("i.category_id = ?")
            parameters.append(form.category.data)

        if form.subcategory.data:
            filter_queries.append("i.subcategory_id = ?")
            parameters.append(form.subcategory.data)

        if filter_queries:
            query += " WHERE "
            query += " AND ".join(filter_queries)

        if form.price.data:
            if form.price.data == 1:
                query += " ORDER BY i.price DESC"
            if form.price.data == 2:
                query += " ORDER BY i.price"
        else:
            query += " ORDER BY i.id DESC"

        items_from_db = c.execute(query, tuple(parameters))
        print(query)

    else:
        items_from_db = c.execute(query + " ORDER BY i.id DESC")

    items = []
    for row in items_from_db:  # create item dictionary for easier reference
        item = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "price": row[3],
            "image": row[4],
            "category": row[5],
            "subcategory": row[6]
        }
        items.append(item)  # add item to items list

    return render_template("home.html", items=items, form=form)

@app.route("/uploads/<filename>")
def uploads(filename):
    return send_from_directory(app.config["IMAGE_UPLOADS"], filename)


# CREATE ITEM
@app.route("/item/new", methods=["GET", "POST"])
def new_item():
    # pdb.set_trace() # stops package here to inspect post request
    conn = get_db()
    c = conn.cursor()
    form = NewItemForm()

    # Categories from database added as choices in the form
    c.execute("SELECT id, name FROM categories")
    categories = c.fetchall()
    form.category.choices = categories

    # Subcategories from database added as choices in the form
    c.execute("""SELECT id, name FROM subcategories
                    WHERE category_id = ?""",
                    (1,)
    )
    subcategories = c.fetchall()
    form.subcategory.choices = subcategories


    if form.validate_on_submit():

        format = "%Y$m$dT%H$M%S"
        now = datetime.datetime.utcnow().strftime(format)
        random_string = token_hex(2)
        filename = random_string + "_" + now + "_" + form.image.data.filename
        filename = secure_filename(filename)
        form.image.data.save(os.path.join(app.config["IMAGE_UPLOADS"], filename))

        c.execute("""INSERT INTO items (title, description, price, image, category_id, subcategory_id) VALUES (?,?,?,?,?,?)""",
                  (form.title.data, form.description.data, float(form.price.data), filename, form.category.data, form.subcategory.data))
        conn.commit()

        flash("Item {} has been successfully submitted".format(request.form.get("title")), "success")
        return redirect(url_for("home"))

    if form.errors:
        flash("{}".format(form.errors), "danger")
    return render_template("new_item.html", form=form)


def get_db():
    db = getattr(g, "_database", None)  # get current database object
    if db is None:  # if connection to db doesn't exist, create one
        db = g._database = sqlite3.connect("db/webshop.db")
    return db


@app.teardown_appcontext  # closes connection when request is over
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()
