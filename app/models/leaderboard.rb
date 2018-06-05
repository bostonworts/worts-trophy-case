class Leaderboard
  def initialize(season:)
    @season = season
  end

  def results
    User.with_trophies(season).map do |user|
      Result.new(user)
    end.sort.reverse
  end

  private

  attr_reader :season

  class Result
    include Comparable

    delegate :id, to: :user, prefix: true

    def initialize(user)
      @user = user
    end

    def <=>(other)
      score <=> other.score
    end

    def brewer_name
      user.full_name
    end

    def score
      # TODO - scope by season
      user.trophies.sum(&:leaderboard_score)
    end

    private

    attr_reader :user
  end
end
