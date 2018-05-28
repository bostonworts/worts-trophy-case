class AddCompetitionToTrophies < ActiveRecord::Migration[5.2]
  def change
    add_reference :trophies, :competition, foreign_key: true
  end
end
