class TrophiesController < ApplicationController
  before_action :require_user!, except: [:index]

  def index
  end

  def new
  end
end
