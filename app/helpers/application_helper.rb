module ApplicationHelper
  def nav_link(title, path)
    is_selected = request.path == path || request.path == "/" && path == trophies_path
    link_to path, class: "menu-item#{is_selected ? " selected" : ""}" do
      title
    end
  end
end
