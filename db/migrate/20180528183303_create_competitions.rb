class CreateCompetitions < ActiveRecord::Migration[5.2]
  def change
    create_table :competitions do |t|
      t.string :url, null: false
      t.date :date, null: false
      t.string :name, null: false
      t.string :competition_type, null: false

      t.timestamps
    end
  end
end
