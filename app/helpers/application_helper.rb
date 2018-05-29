module ApplicationHelper
  def nav_link(path, &block)
    is_selected = current_page?(path)
    link_to path, class: "menu-item#{is_selected ? " selected" : ""}", &block
  end
end
