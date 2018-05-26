class CreateTrophies < ActiveRecord::Migration[5.2]
  def change
    create_table :trophies do |t|
      t.integer :bjcp_score, null: false
      t.date :competition_date, null: false
      t.string :competition_url, null: false
      t.integer :place, null: true
      t.string :place_context, null: true
      t.string :recipe_url, null: true
      t.references :user, foreign_key: true

      t.timestamps
    end
  end
end
