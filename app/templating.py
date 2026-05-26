from fastapi.templating import Jinja2Templates

from app.services.display import humanize_label
from app.services.placements import place_label


templates = Jinja2Templates(directory="app/templates")
templates.env.filters["humanize"] = humanize_label
templates.env.filters["place_label"] = place_label
