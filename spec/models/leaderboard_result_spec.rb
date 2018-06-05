require "rails_helper"

describe LeaderboardResult do
  describe "#score" do
    it "doesn't take into account trophies from other seasons" do
      user = create(:user)
      current_season = Season.current
      current_season_comp = create(:competition, date: current_season.start_date + 20)
      last_season_comp = create(:competition, date: current_season.start_date - 20)

      create_pair(:trophy, :category_1st, competition: current_season_comp, user: user)
      create_pair(:trophy, :best_of_show_1st, competition: last_season_comp, user: user)

      result = LeaderboardResult.new(user, season: current_season)

      expect(result.score).to eq(6)
    end
  end
end
