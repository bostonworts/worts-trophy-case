class CreateCategories < ActiveRecord::Migration[5.2]
  def change
    create_table :categories do |t|
      t.string :bjcp_id, null: false
      t.string :name, null: false
      t.integer :year, null: false

      t.timestamps
    end
  end
end
