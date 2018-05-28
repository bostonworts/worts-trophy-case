class CompetitionsController < ApplicationController
  def new
    @competition = Competition.new
  end

  def create
    @competition = Competition.new(competition_params)

    if @competition.save
      redirect_to root_path, notice: "Competition successfully created!"
    else
      render "new"
    end
  end

  private

  def competition_params
    params.require(:competition).permit(
      :date,
      :competition_type,
      :name,
      :url,
    )
  end
end
