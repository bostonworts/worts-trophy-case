class TrophiesController < ApplicationController
  before_action :require_user!, except: [:index]

  def index
    @trophies = Trophy.joins(:competition).merge(Competition.order(date: :desc))
  end

  def new
    @trophy = Trophy.new
  end

  def create
    @trophy = Trophy.new(trophy_params)

    if @trophy.save
      redirect_to root_path, notice: "Your trophy was created!"
    else
      render "new"
    end
  end

  def update
    @trophy = Trophy.find(params[:id])

    if @trophy.update(trophy_params)
      redirect_to root_path, notice: "Trophy successfully updated!"
    else
      render "new"
    end
  end

  def edit
    @trophy = Trophy.find(params[:id])
  end

  def destroy
    trophy = Trophy.find(params[:id])

    if current_user.can_delete?(trophy) && trophy.destroy
      redirect_to root_path, notice: "Trophy successfully deleted"
    else
      redirect_to root_path, error: "Trophy could not be deleted"
    end
  end

  private

  def trophy_params
    params.require(:trophy).permit(
      :bjcp_score,
      :competition_id,
      :photo,
      :place,
      :place_context,
      :recipe_url,
      :subcategory_id,
    ).merge(user: current_user)
  end
end
