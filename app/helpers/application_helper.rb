module ApplicationHelper
  def nav_link(title, path)
    is_selected = request.path == path || request.path == "/" && path == trophies_path
    link_to title, path, class: "UnderlineNav-item#{is_selected ? " selected" : ""}"
  end
end
