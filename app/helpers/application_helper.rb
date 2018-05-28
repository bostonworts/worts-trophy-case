module ApplicationHelper
  def nav_link(path, &block)
    is_selected = request.path == path || request.path == "/" && path == trophies_path
    link_to path, class: "menu-item#{is_selected ? " selected" : ""}", &block
  end
end
