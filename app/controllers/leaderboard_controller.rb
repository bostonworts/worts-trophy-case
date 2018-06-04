class LeaderboardController < ApplicationController
  def show
    @leaderboard = Leaderboard.new
  end
end
