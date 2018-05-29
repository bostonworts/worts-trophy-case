module ApplicationHelper
  def nav_link(path, &block)
    is_selected = current_page?(path)

    if path == "/competitions"
      is_selected ||= current_page?("/")
    end

    link_to path, class: "menu-item#{is_selected ? " selected" : ""}", &block
  end
end
