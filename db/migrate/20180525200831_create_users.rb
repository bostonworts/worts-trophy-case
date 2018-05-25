class CreateUsers < ActiveRecord::Migration[5.2]
  def change
    create_table :users do |t|
      t.string :full_name, null: false
      t.string :email, null: false
      t.boolean :admin, null: false

      t.timestamps
      t.index :email, unique: true
    end
  end
end
