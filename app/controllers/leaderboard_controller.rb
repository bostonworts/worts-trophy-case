class LeaderboardController < ApplicationController
  def show
    @leaderboard = Leaderboard.new
    @season = if params[:season]
                Season.from_param(params.fetch(:season))
              else
                Season.current
              end
  end
end
