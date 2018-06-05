class LeaderboardResult
  include Comparable

  delegate :id, to: :user, prefix: true

  def initialize(user, season:)
    @user = user
    @season = season
  end

  def <=>(other)
    score <=> other.score
  end

  def brewer_name
    user.full_name
  end

  def score
    user.trophies.in_season(season).sum(&:leaderboard_score)
  end

  private

  attr_reader :season, :user
end
