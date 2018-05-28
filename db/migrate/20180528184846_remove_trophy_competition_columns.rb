class RemoveTrophyCompetitionColumns < ActiveRecord::Migration[5.2]
  def change
    remove_column :trophies, :competition_date
    remove_column :trophies, :competition_url
  end
end
