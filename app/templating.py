from fastapi.templating import Jinja2Templates

from app.services.placements import place_label


templates = Jinja2Templates(directory="app/templates")
templates.env.filters["place_label"] = place_label
