require "rails_helper"

describe Leaderboard do
  describe "#results" do
    it "doesn't include users with no trophies" do
      create(:user)
      leaderboard = Leaderboard.new(season: Season.current)
      expect(leaderboard.results).to be_empty
    end
  end
end
