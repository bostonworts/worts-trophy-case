namespace :bjcp do
  task load_styles: :environment do
    json = JSON.parse(File.read("config/styleguides/2015.json"))
    classes = json.dig("styleguide", "class")
    categories = classes.flat_map do |klass|
      klass["category"].map do |category|
        category.slice("id", "name", "subcategory")
        {
          bjcp_id: category["id"],
          name: category["name"],
          subcategories: category["subcategory"].map do |sub|
            { bjcp_id: sub["id"], name: sub["name"] }
          end
        }
      end
    end

    categories.each do |cat_json|
      category = Category.create_with(cat_json.slice(:name)).find_or_create_by(
        cat_json.slice(:bjcp_id).merge(year: 2015)
      )
      cat_json[:subcategories].each do |subcat_json|
        Subcategory.create_with(subcat_json.slice(:name)).find_or_create_by(
          subcat_json.slice(:bjcp_id).merge(
            category: category
          )
        )
      end
    end

    # Add custom categories
    [
      { bjcp_id: "35", subcat_id: "35A", name: "New England IPA (Custom Style)" },
      { bjcp_id: "36", subcat_id: "36A", name: "Double New England IPA (Custom Style)"},
    ].each do |custom_style|
      cat = Category.find_or_create_by!(custom_style.slice(:bjcp_id, :name).merge(year: 2015))
      Subcategory.find_or_create_by!(custom_style.slice(:name).merge(
        bjcp_id: custom_style[:subcat_id],
        category: cat,
      ))
    end

    puts "#{Category.count} categories and #{Subcategory.count} subcategories imported"
  end
end
