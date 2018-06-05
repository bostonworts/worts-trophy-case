class Leaderboard
  def initialize(season:)
    @season = season
  end

  def results
    User.with_trophies(season).map do |user|
      LeaderboardResult.new(user, season: season)
    end.sort.reverse
  end

  private

  attr_reader :season
end
