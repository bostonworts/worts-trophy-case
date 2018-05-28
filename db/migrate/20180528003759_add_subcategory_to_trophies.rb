class AddSubcategoryToTrophies < ActiveRecord::Migration[5.2]
  def change
    add_reference :trophies, :subcategory, foreign_key: true
  end
end
