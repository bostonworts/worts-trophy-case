class CreateSubcategories < ActiveRecord::Migration[5.2]
  def change
    create_table :subcategories do |t|
      t.string :bjcp_id, null: false
      t.string :name, null: false
      t.references :category, foreign_key: true, null: false

      t.timestamps
    end
  end
end
