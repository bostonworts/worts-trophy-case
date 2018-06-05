class LeaderboardController < ApplicationController
  def show
    @season = if params[:season]
                Season.from_param(params.fetch(:season))
              else
                Season.current
              end
    @leaderboard = Leaderboard.new(season: @season)
  end
end
