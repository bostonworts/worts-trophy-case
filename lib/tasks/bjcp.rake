namespace :bjcp do
  task :load_styles do
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

    puts "#{Category.count} categories and #{Subcategory.count} subcategories imported"
  end
end
